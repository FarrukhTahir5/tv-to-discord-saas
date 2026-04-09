"""
LemonSqueezy billing routes — checkout redirect + webhook handler.
"""

import json
import structlog

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.services.lemonsqueezy_svc import create_checkout, verify_webhook_signature

logger = structlog.get_logger()
router = APIRouter(prefix="/billing", tags=["billing"])


# ------------------------------------------------------------------
# Create checkout → redirect to LemonSqueezy hosted page
# ------------------------------------------------------------------
@router.post("/create-checkout")
async def billing_create_checkout(
    request: Request,
    user: User = Depends(get_current_user),
):
    form = await request.form()
    plan_type = form.get("plan_type") or "monthly"

    variant_id = (
        settings.lemonsqueezy_variant_id_yearly
        if plan_type == "yearly"
        else settings.lemonsqueezy_variant_id_monthly
    )

    try:
        checkout_url = await create_checkout(
            user_id=user.id,
            user_email=user.email,
            variant_id=variant_id,
        )
        return RedirectResponse(url=checkout_url, status_code=303)

    except Exception as e:
        logger.error("lemonsqueezy_checkout_failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------
# LemonSqueezy Webhook — verify signature, update user plan
# ------------------------------------------------------------------
@router.post("/lemonsqueezy-webhook")
async def lemonsqueezy_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    raw_body = await request.body()
    signature = request.headers.get("x-signature", "")

    if not verify_webhook_signature(raw_body, signature):
        raise HTTPException(400, "Invalid webhook signature")

    payload = json.loads(raw_body)
    meta = payload.get("meta", {})
    event_name = meta.get("event_name", "")
    custom_data = meta.get("custom_data", {})

    data = payload.get("data", {})
    attrs = data.get("attributes", {})

    # Extract identifiers
    user_email = attrs.get("user_email")
    customer_id = str(attrs.get("customer_id", ""))
    subscription_id = str(data.get("id", ""))
    status = attrs.get("status", "")

    # Try to find user by custom_data user_id first, then by email
    user = None
    user_id = custom_data.get("user_id")
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if not user and user_email:
        result = await db.execute(select(User).where(User.email == user_email))
        user = result.scalar_one_or_none()

    if not user:
        logger.warn("lemonsqueezy_webhook_user_not_found", email=user_email, user_id=user_id)
        return {"received": True, "skipped": "User not found"}

    # Handle subscription events
    if event_name in ("subscription_created", "subscription_updated", "subscription_resumed"):
        if status in ("active", "on_trial", "paused"):
            await _set_plan(db, user, "pro", "active", customer_id, subscription_id)
            logger.info("user_upgraded_to_pro", user_id=user.id, ls_event=event_name)

    elif event_name in ("subscription_cancelled", "subscription_expired"):
        await _set_plan(db, user, "free", "inactive", customer_id, subscription_id)
        logger.info("user_downgraded_to_free", user_id=user.id, ls_event=event_name)

    elif event_name == "subscription_payment_failed":
        if status in ("past_due", "unpaid"):
            await _set_plan(db, user, "free", "inactive", customer_id, subscription_id)
            logger.info("user_payment_failed_downgraded", user_id=user.id)

    return {"received": True}


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------
async def _set_plan(
    db: AsyncSession,
    user: User,
    plan: str,
    status: str,
    customer_id: str = "",
    subscription_id: str = "",
):
    user.plan = plan
    user.subscription_status = status
    if customer_id:
        user.ls_customer_id = customer_id
    if subscription_id:
        user.ls_subscription_id = subscription_id
    user.daily_limit = (
        settings.pro_alerts_per_day if plan == "pro" else settings.free_alerts_per_day
    )
    await db.commit()
