import hashlib
import re
import time

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.db import get_db
from app.models import AlertLog, User, UserWebhook
from app.services.queue_svc import notify_worker



router = APIRouter(tags=["webhook"])
limiter = Limiter(key_func=get_remote_address)


def make_idempotency_key(user_id: str, raw_text: str) -> str:
    """Hash user + content + 10-second bucket to catch near-duplicates."""
    rounded = int(time.time() / 10) * 10
    key = f"{user_id}:{raw_text.strip()}:{rounded}"
    return hashlib.sha256(key.encode()).hexdigest()[:32]


async def get_user_by_token(token: str, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.webhook_token == token)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "Invalid webhook token")
    return user


@router.post("/webhook/{token}")
@limiter.limit("20/minute")
async def receive_webhook(
    token: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # --- 1. Reject oversized payloads ---
    content_length = request.headers.get("content-length", 0)
    if int(content_length) > 5120:  # 5KB
        raise HTTPException(413, "Payload too large")

    # --- 2. Parse body (text/plain OR JSON) ---
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        raw_text = (
            body.get("message")
            or body.get("content")
            or body.get("alert_message", "")
        )
    else:
        raw_text = (await request.body()).decode("utf-8", errors="replace")

    raw_text = raw_text.strip()
    if not raw_text:
        raise HTTPException(400, "Empty alert body")

    # --- 3. Lookup user ---
    user = await get_user_by_token(token, db)


    # Check if user has ANY webhook (legacy or new table)
    has_webhook = False
    if user.discord_webhook_url:
        has_webhook = True
    else:
        wh_check = await db.execute(
            select(UserWebhook).where(UserWebhook.user_id == user.id).limit(1)
        )
        if wh_check.scalar_one_or_none():
            has_webhook = True

    if not has_webhook:
        raise HTTPException(400, "No Discord webhooks configured")


    # --- 4. Idempotency check ---
    idem_key = make_idempotency_key(user.id, raw_text)
    existing = await db.execute(
        select(AlertLog).where(AlertLog.idempotency_key == idem_key)
    )
    if existing.scalar_one_or_none():
        return {"status": "duplicate", "message": "Alert already queued"}

    # --- 5. Create log entry (status=queued IS the queue) ---
    alert = AlertLog(
        user_id=user.id,
        idempotency_key=idem_key,
        raw_text=raw_text,
        status="queued",
        request_ip=request.client.host if request.client else None,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)

    # --- 6. Notify worker (non-blocking) ---
    await notify_worker(alert.id)

    return {"status": "queued", "alert_id": alert.id}
