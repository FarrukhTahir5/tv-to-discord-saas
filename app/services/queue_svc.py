"""
Queue service — bridges the API and Worker processes.

Strategy:
  - The API writes alerts with status="queued" to the DB (already done in webhook.py).
  - The Worker polls the DB for queued alerts and processes them.
  - Optional: if REDIS_URL is set, use Redis pub/sub to notify the worker
    instantly instead of polling. Falls back to polling otherwise.

This design works across separate processes with no shared memory.
"""

import asyncio
import datetime
import json
import time
import logging
from typing import Optional

from sqlalchemy import select, update
from app.services.parser import parse_alert
from app.services.screenshot import take_screenshot
from app.services.discord_svc import post_to_discord
from app.services.limits import check_and_increment_usage
from app.db import AsyncSessionLocal
from app.models import AlertLog, User, UserWebhook

from app.config import settings

logger = logging.getLogger(__name__)

_worker_task: Optional[asyncio.Task] = None
_redis_listener_task: Optional[asyncio.Task] = None
_notify_event = asyncio.Event()

# Alerts processed in parallel (one browser tab each)
_slots: Optional[asyncio.Semaphore] = None
_running: set[asyncio.Task] = set()

# The screenshot gets its own limit so the text alert is still posted
# if TradingView is slow; the job limit is a backstop for everything else.
SCREENSHOT_TIMEOUT_S = 100
JOB_TIMEOUT_S = 150
STALE_PROCESSING_MIN = 10

# ---- Redis (optional instant notification) -------------------------

_redis = None
CHANNEL = "chartalert:jobs"


async def _init_redis():
    """Try to connect to Redis. Returns None if unavailable."""
    global _redis
    if not settings.redis_url:
        return
    try:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        logger.info("Redis connected at %s", settings.redis_url)
    except Exception as e:
        logger.warning("Redis unavailable, falling back to DB polling: %s", e)
        _redis = None


async def notify_worker(alert_id: str):
    """
    Called by the API after inserting a queued alert.
    If Redis is available, publish a notification.
    Otherwise, the worker will pick it up on next poll cycle.
    """
    if _redis:
        try:
            await _redis.publish(CHANNEL, json.dumps({"alert_id": alert_id}))
        except Exception:
            pass  # Worker will poll anyway
    # Also set the local event in case we're in "both" mode
    _notify_event.set()


# ---- Worker lifecycle ----------------------------------------------

async def start_worker():
    """Launch the background worker loop."""
    global _worker_task, _redis_listener_task, _slots
    await _init_redis()
    await _fail_stale_jobs()
    _slots = asyncio.Semaphore(settings.screenshot_concurrency)
    _worker_task = asyncio.create_task(_worker_loop())

    if _redis:
        _redis_listener_task = asyncio.create_task(_redis_subscribe_loop())

    logger.info(
        "Queue worker started (poll_interval=2s, parallel=%d)",
        settings.screenshot_concurrency,
    )


async def stop_worker():
    """Cancel the worker tasks."""
    for task in (_worker_task, _redis_listener_task, *_running):
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    if _redis:
        await _redis.aclose()
    logger.info("Queue worker stopped")


# ---- Worker main loops ---------------------------------------------

async def _worker_loop():
    """Claim queued alerts from the DB and process up to N at a time."""
    while True:
        try:
            await _slots.acquire()
            try:
                alert = await _claim_next()
            except Exception:
                _slots.release()
                raise
            if alert is None:
                _slots.release()
                # Wait for either a Redis notification or poll timeout
                _notify_event.clear()
                try:
                    await asyncio.wait_for(_notify_event.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    pass  # Normal — just poll again
                continue
            task = asyncio.create_task(_run_job(alert))
            _running.add(task)
            task.add_done_callback(_job_done)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Worker loop error: %s", e, exc_info=True)
            await asyncio.sleep(5)  # Back off on error


def _job_done(task: asyncio.Task):
    _running.discard(task)
    _slots.release()


async def _fail_stale_jobs():
    """Alerts left 'processing' by a crash or restart would otherwise sit there forever."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=STALE_PROCESSING_MIN)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(AlertLog)
            .where(AlertLog.status == "processing", AlertLog.created_at < cutoff)
            .values(status="failed", error_stage="timeout", error_message="Worker restarted")
        )
        await db.commit()
    if result.rowcount:
        logger.warning("Marked %d stale processing alerts as failed", result.rowcount)


async def _redis_subscribe_loop():
    """Listen for Redis pub/sub notifications to wake the worker instantly."""
    try:
        pubsub = _redis.pubsub()
        await pubsub.subscribe(CHANNEL)
        async for message in pubsub.listen():
            if message["type"] == "message":
                _notify_event.set()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning("Redis subscriber lost: %s", e)


async def _claim_next() -> Optional[AlertLog]:
    """
    Atomically claim the oldest queued alert. SKIP LOCKED stops
    parallel jobs (or several workers) from grabbing the same one.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AlertLog)
            .where(AlertLog.status == "queued")
            .order_by(AlertLog.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        alert = result.scalar_one_or_none()
        if not alert:
            return None
        alert.status = "processing"
        await db.commit()
        return alert


async def _run_job(alert: AlertLog):
    try:
        await asyncio.wait_for(_process_alert(alert), timeout=JOB_TIMEOUT_S)
    except asyncio.TimeoutError:
        logger.error("Job %s timed out after %ss", alert.id, JOB_TIMEOUT_S)
        await _update_alert(
            alert.id, status="failed",
            error_stage="timeout", error_message=f"Job timed out after {JOB_TIMEOUT_S}s",
        )
    except Exception as e:
        logger.error("Job %s exception: %s", alert.id, e, exc_info=True)
        await _update_alert(
            alert.id, status="failed",
            error_stage="unknown", error_message=str(e),
        )


async def _process_alert(alert: AlertLog):
    """Full processing pipeline for one alert."""
    start_time = time.monotonic()

    # Fetch the user
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).where(User.id == alert.user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await _update_alert(
                alert.id, status="failed",
                error_stage="parse", error_message="User not found",
            )
            return

    # --- Check usage limit ---
    allowed = await check_and_increment_usage(user.id)
    if not allowed:
        await _update_alert(
            alert.id, status="failed",
            error_stage="billing", error_message="Daily limit reached",
        )
        return

    # --- Parse ticker ---
    parsed = parse_alert(
        alert.raw_text,
        user.default_exchange,
        user.default_symbol,
        user.default_interval,
    )
    await _update_alert(
        alert.id,
        parsed_symbol=parsed.symbol,
        parsed_message=parsed.message,
    )

    # --- Screenshot ---
    screenshot = None
    if parsed.symbol:
        try:
            screenshot = await asyncio.wait_for(
                take_screenshot(
                    parsed.symbol,
                    interval=parsed.interval or "D",  # daily unless the user chose otherwise
                    layout_id=user.chart_layout_id,
                ),
                timeout=SCREENSHOT_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.error("Screenshot for %s timed out after %ss", parsed.symbol, SCREENSHOT_TIMEOUT_S)
        if screenshot:
            await _update_alert(alert.id, status="screenshot_ok")

    # --- Discord post ---
    

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserWebhook)
            .where(UserWebhook.user_id == user.id, UserWebhook.is_active == True)
        )
        webhooks = result.scalars().all()

    if not webhooks:
        # Fallback to legacy column if no new webhooks exist
        if user.discord_webhook_url:
            webhooks = [UserWebhook(url=user.discord_webhook_url, name="Legacy Channel")]
        else:
            await _update_alert(
                alert.id, status="failed",
                error_stage="discord", error_message="No Discord webhooks configured",
            )
            return

    results = []
    for wh in webhooks:
        res = await post_to_discord(
            wh.url,
            symbol=parsed.ticker or parsed.symbol or "Unknown",
            message=parsed.message,
            screenshot_bytes=screenshot,
            app_name=settings.app_name,
        )
        results.append(res)

    success = any(r.success for r in results)
    status_code = next((r.status_code for r in results if not r.success), 200)
    error_msg = "; ".join([r.error for r in results if r.error]) if not success else None

    elapsed_ms = int((time.monotonic() - start_time) * 1000)

    if success and not screenshot:
        # Delivered, but as text only — tracked so the admin panel can show it
        error_stage, error_msg = "screenshot", "Delivered without chart"
    else:
        error_stage = None if success else "discord"

    await _update_alert(
        alert.id,
        status="discord_ok" if success else "failed",
        error_stage=error_stage,
        error_message=error_msg,
        discord_status_code=status_code,
        processing_time_ms=elapsed_ms,
    )

    logger.info(
        "job.completed alert_id=%s symbol=%s ok=%s targets=%d ms=%d",
        alert.id, parsed.symbol, success, len(webhooks), elapsed_ms,
    )



async def _update_alert(alert_id: str, **kwargs):
    """Update an AlertLog record with the given fields."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(AlertLog).where(AlertLog.id == alert_id)
        )
        alert = result.scalar_one_or_none()
        if alert:
            for key, val in kwargs.items():
                setattr(alert, key, val)
            await db.commit()
