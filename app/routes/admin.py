from datetime import datetime, time, timedelta
from urllib.parse import urlencode

import aiohttp
import structlog
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from app.db import get_db
from app.models import User, AlertLog, UserWebhook

from app.services.auth import get_current_user
from app.services.lemonsqueezy_svc import apply_subscription, get_subscription
from app.config import settings
from app.templates_config import templates

logger = structlog.get_logger()
router = APIRouter(prefix="/admin", tags=["admin"])

FILTERS = {
    "all": "All",
    "paying": "Paying",
    "cancelling": "Cancelling",
    "trial": "On trial",
    "free": "Free",
    "unused": "Never sent an alert",
}


def admin_required(user: User = Depends(get_current_user)):
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _back(path: str = "/admin/", **params) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(url=f"{path}{query}", status_code=303)


def _is_paying(u: User) -> bool:
    return bool(u.ls_subscription_id) and u.effective_plan == "pro" and not u.on_trial and not u.is_admin


def _is_cancelling(u: User, now: datetime) -> bool:
    return u.subscription_status == "cancelled" and bool(u.subscription_ends_at) and u.subscription_ends_at > now


def _is_deletable(u: User) -> bool:
    """Never delete the admin or anyone whose paid access is still running."""
    return not u.is_admin and not _is_paying(u)


async def _get_user(db: AsyncSession, user_id: str) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise HTTPException(404, "User not found")
    return u


async def _worker_status() -> str:
    """'ok' | 'down' | 'unknown' — browser health of the screenshot worker."""
    if settings.run_mode == "both":
        from app.services.screenshot import _browser
        return "ok" if _browser is not None and _browser.is_connected() else "down"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                settings.worker_health_url, timeout=aiohttp.ClientTimeout(total=3)
            ) as resp:
                data = await resp.json()
                return "ok" if data.get("browser_running") else "down"
    except Exception:
        return "down"


async def _delete_users(db: AsyncSession, users: list[User]) -> int:
    ids = [u.id for u in users]
    if not ids:
        return 0
    await db.execute(delete(AlertLog).where(AlertLog.user_id.in_(ids)))
    await db.execute(delete(UserWebhook).where(UserWebhook.user_id.in_(ids)))
    await db.execute(delete(User).where(User.id.in_(ids)))
    await db.commit()
    return len(ids)


# ------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------
@router.get("/")
async def admin_dashboard(
    request: Request,
    filter: str = "all",
    q: str = "",
    msg: str = "",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), time.min)
    day_ago = now - timedelta(hours=24)

    all_users = (
        await db.execute(select(User).order_by(User.created_at.desc()))
    ).scalars().all()

    # Per-user alert totals and last alert time
    alert_rows = (
        await db.execute(
            select(AlertLog.user_id, func.count(AlertLog.id), func.max(AlertLog.created_at))
            .group_by(AlertLog.user_id)
        )
    ).all()
    alert_stats = {uid: {"count": c, "last": last} for uid, c, last in alert_rows}

    webhook_rows = (
        await db.execute(
            select(UserWebhook.user_id, func.count(UserWebhook.id)).group_by(UserWebhook.user_id)
        )
    ).all()
    webhook_counts = dict(webhook_rows)

    def has_alerts(u):
        return u.id in alert_stats

    # Stats
    paying = [u for u in all_users if _is_paying(u)]
    stats = {
        "total_users": len(all_users),
        "signups_7d": sum(1 for u in all_users if u.created_at and u.created_at >= now - timedelta(days=7)),
        "signups_30d": sum(1 for u in all_users if u.created_at and u.created_at >= now - timedelta(days=30)),
        "paying": len(paying),
        "cancelling": sum(1 for u in all_users if _is_cancelling(u, now)),
        "on_trial": sum(1 for u in all_users if u.on_trial and not u.is_admin),
        "activated": sum(1 for u in all_users if has_alerts(u)),
        "unused": sum(1 for u in all_users if not has_alerts(u) and _is_deletable(u)),
    }

    stats["alerts_today"] = (
        await db.execute(select(func.count(AlertLog.id)).where(AlertLog.created_at >= today_start))
    ).scalar()
    stats["alerts_24h"] = (
        await db.execute(select(func.count(AlertLog.id)).where(AlertLog.created_at >= day_ago))
    ).scalar()
    stats["failed_24h"] = (
        await db.execute(
            select(func.count(AlertLog.id)).where(
                AlertLog.created_at >= day_ago, AlertLog.status == "failed"
            )
        )
    ).scalar()
    stats["no_chart_24h"] = (
        await db.execute(
            select(func.count(AlertLog.id)).where(
                AlertLog.created_at >= day_ago,
                AlertLog.status == "discord_ok",
                AlertLog.error_stage == "screenshot",
            )
        )
    ).scalar()
    stats["total_alerts"] = (await db.execute(select(func.count(AlertLog.id)))).scalar()

    # Queue health
    queued = (
        await db.execute(
            select(func.count(AlertLog.id), func.min(AlertLog.created_at)).where(
                AlertLog.status.in_(("queued", "processing"))
            )
        )
    ).one()
    stats["queue_pending"] = queued[0]
    stats["queue_oldest_min"] = int((now - queued[1]).total_seconds() // 60) if queued[1] else None
    stats["worker"] = await _worker_status()

    # Filter + search
    if filter == "paying":
        users = paying
    elif filter == "cancelling":
        users = [u for u in all_users if _is_cancelling(u, now)]
    elif filter == "trial":
        users = [u for u in all_users if u.on_trial and not u.is_admin]
    elif filter == "free":
        users = [u for u in all_users if u.effective_plan == "free"]
    elif filter == "unused":
        users = [u for u in all_users if not has_alerts(u) and _is_deletable(u)]
    else:
        filter = "all"
        users = list(all_users)
    if q:
        users = [u for u in users if q.lower() in u.email.lower()]

    recent_failures = (
        await db.execute(
            select(AlertLog, User.email)
            .join(User, User.id == AlertLog.user_id)
            .where(AlertLog.status == "failed")
            .order_by(AlertLog.created_at.desc())
            .limit(15)
        )
    ).all()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "stats": stats,
            "users": users,
            "alert_stats": alert_stats,
            "webhook_counts": webhook_counts,
            "deletable": {u.id for u in all_users if _is_deletable(u)},
            "paying_ids": {u.id for u in paying},
            "recent_failures": recent_failures,
            "filters": FILTERS,
            "active_filter": filter,
            "q": q,
            "msg": msg,
            "now": now,
            "title": "Admin Dashboard",
        },
    )


# ------------------------------------------------------------------
# User detail
# ------------------------------------------------------------------
@router.get("/users/{user_id}")
async def admin_user_detail(
    user_id: str,
    request: Request,
    msg: str = "",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    now = datetime.utcnow()
    u = await _get_user(db, user_id)
    webhooks = (
        await db.execute(select(UserWebhook).where(UserWebhook.user_id == u.id))
    ).scalars().all()
    alerts = (
        await db.execute(
            select(AlertLog)
            .where(AlertLog.user_id == u.id)
            .order_by(AlertLog.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    total_alerts = (
        await db.execute(select(func.count(AlertLog.id)).where(AlertLog.user_id == u.id))
    ).scalar()

    return templates.TemplateResponse(
        "admin_user.html",
        {
            "request": request,
            "user": admin,
            "u": u,
            "webhooks": webhooks,
            "alerts": alerts,
            "total_alerts": total_alerts,
            "is_paying": _is_paying(u),
            "deletable": _is_deletable(u),
            "msg": msg,
            "now": now,
            "title": f"Admin · {u.email}",
        },
    )


# ------------------------------------------------------------------
# User actions
# ------------------------------------------------------------------
@router.post("/users/{user_id}/trial")
async def admin_grant_trial(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    form = await request.form()
    try:
        days = int(form.get("days", 7))
    except ValueError:
        raise HTTPException(400, "Invalid number of days")
    if not 1 <= days <= 365:
        raise HTTPException(400, "Days must be between 1 and 365")

    u = await _get_user(db, user_id)
    now = datetime.utcnow()
    start = u.trial_expires_at if u.trial_expires_at and u.trial_expires_at > now else now
    u.trial_expires_at = start + timedelta(days=days)
    await db.commit()
    logger.info("admin_trial_granted", admin=admin.email, user=u.email, days=days)
    return _back(f"/admin/users/{u.id}", msg=f"Trial extended by {days} days")


@router.post("/users/{user_id}/end-trial")
async def admin_end_trial(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    u = await _get_user(db, user_id)
    u.trial_expires_at = None
    await db.commit()
    logger.info("admin_trial_ended", admin=admin.email, user=u.email)
    return _back(f"/admin/users/{u.id}", msg="Trial ended")


@router.post("/users/{user_id}/plan")
async def admin_set_plan(
    user_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    """Manual override, e.g. free Pro for a partner. LemonSqueezy events still override it later."""
    form = await request.form()
    plan = form.get("plan")
    if plan not in ("pro", "free"):
        raise HTTPException(400, "Invalid plan")

    u = await _get_user(db, user_id)
    u.plan = plan
    u.subscription_ends_at = None
    if not u.ls_subscription_id:
        u.subscription_status = "manual" if plan == "pro" else "inactive"
    u.daily_limit = settings.pro_alerts_per_day if plan == "pro" else settings.free_alerts_per_day
    await db.commit()
    logger.info("admin_plan_set", admin=admin.email, user=u.email, plan=plan)
    return _back(f"/admin/users/{u.id}", msg=f"Plan set to {plan}")


@router.post("/users/{user_id}/reset-usage")
async def admin_reset_usage(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    u = await _get_user(db, user_id)
    u.alerts_used_today = 0
    await db.commit()
    return _back(f"/admin/users/{u.id}", msg="Today's usage reset")


@router.post("/users/{user_id}/sync")
async def admin_sync_subscription(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    """Pull the subscription's real status from LemonSqueezy (fixes missed webhooks)."""
    u = await _get_user(db, user_id)
    if not u.ls_subscription_id:
        return _back(f"/admin/users/{u.id}", msg="No LemonSqueezy subscription on this user")
    try:
        attrs = await get_subscription(u.ls_subscription_id)
    except Exception as e:
        logger.error("admin_sync_failed", user=u.email, error=str(e))
        return _back(f"/admin/users/{u.id}", msg=f"Sync failed: {e}")
    status = apply_subscription(u, attrs, u.ls_subscription_id)
    await db.commit()
    logger.info("admin_sync", admin=admin.email, user=u.email, status=status)
    return _back(f"/admin/users/{u.id}", msg=f"Synced from LemonSqueezy: {status}")


@router.post("/sync-subscriptions")
async def admin_sync_all(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    users = (
        await db.execute(select(User).where(User.ls_subscription_id.isnot(None)))
    ).scalars().all()
    ok, failed = 0, 0
    for u in users:
        try:
            attrs = await get_subscription(u.ls_subscription_id)
            apply_subscription(u, attrs, u.ls_subscription_id)
            ok += 1
        except Exception as e:
            logger.error("admin_sync_failed", user=u.email, error=str(e))
            failed += 1
    await db.commit()
    return _back(msg=f"Synced {ok} subscriptions" + (f", {failed} failed" if failed else ""))


@router.post("/users/{user_id}/delete")
async def admin_delete_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    u = await _get_user(db, user_id)
    if not _is_deletable(u):
        return _back(f"/admin/users/{u.id}", msg="Can't delete the admin or a user with active paid access")
    email = u.email
    await _delete_users(db, [u])
    logger.info("admin_user_deleted", admin=admin.email, user=email)
    return _back(msg=f"Deleted {email}")


@router.post("/users/bulk-delete")
async def admin_bulk_delete(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    form = await request.form()
    ids = form.getlist("user_ids")
    if not ids:
        return _back(msg="No users selected")

    now = datetime.utcnow()
    users = (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    to_delete = [u for u in users if _is_deletable(u)]
    skipped = len(users) - len(to_delete)
    count = await _delete_users(db, to_delete)
    logger.info("admin_bulk_delete", admin=admin.email, deleted=count, skipped=skipped)
    return _back(
        msg=f"Deleted {count} users" + (f" (skipped {skipped} admin/paying)" if skipped else "")
    )
