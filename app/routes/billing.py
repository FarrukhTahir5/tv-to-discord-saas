"""
LemonSqueezy billing routes — checkout + webhook handler.
"""

import hashlib
import hmac
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.services.lemonsqueezy_svc import create_checkout

router = APIRouter(prefix="/billing", tags=["billing"])


# ------------------------------------------------------------------
# Create checkout → redirect user to LemonSqueezy hosted page
# ------------------------------------------------------------------
@router.post("/create-checkout")
async def billing_create_checkout(
    request: Request,
    user: User = Depends(get_current_user),
):
    form = await request.form()
    variant_id = form.get("variant_id") or settings.lemonsqueezy_variant_id_monthly

    checkout_url = await create_checkout(
        user_id=user.id,
        user_email=user.email,
        variant_id=variant_id,
    )
    return RedirectResponse(url=checkout_url, status_code=303)


# ------------------------------------------------------------------
# LemonSqueezy webhook — verify signature, update user plan
# ------------------------------------------------------------------
@router.post("/lemonsqueezy-webhook")
async def lemonsqueezy_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # 1. Verify webhook signature (HMAC-SHA256)
    raw_body = await request.body()
    sig = request.headers.get("x-signature", "")

    expected = hmac.new(
        settings.lemonsqueezy_webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, sig):
        raise HTTPException(400, "Invalid webhook signature")

    # 2. Parse the event
    payload = await request.json()
    event_name = payload.get("meta", {}).get("event_name", "")
    custom_data = payload.get("meta", {}).get("custom_data", {})
    user_id = custom_data.get("user_id")

    if not user_id:
        return {"received": True, "skipped": "no user_id in custom_data"}

    attrs = payload.get("data", {}).get("attributes", {})

    # 3. Handle events
    if event_name == "subscription_created":
        await _set_plan(
            db,
            user_id=user_id,
            plan="pro",
            ls_customer_id=str(attrs.get("customer_id", "")),
            ls_subscription_id=str(payload["data"]["id"]),
            subscription_status="active",
        )

    elif event_name == "subscription_updated":
        status = attrs.get("status", "active")
        plan = "pro" if status == "active" else "free"
        await _set_plan(
            db,
            user_id=user_id,
            plan=plan,
            subscription_status=status,
        )

    elif event_name in ("subscription_cancelled", "subscription_expired"):
        await _set_plan(
            db,
            user_id=user_id,
            plan="free",
            subscription_status="inactive",
        )

    elif event_name == "subscription_payment_success":
        await _set_plan(
            db,
            user_id=user_id,
            plan="pro",
            subscription_status="active",
        )

    elif event_name == "subscription_payment_failed":
        await _set_plan(
            db,
            user_id=user_id,
            plan="free",
            subscription_status="past_due",
        )

    return {"received": True}


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------
async def _set_plan(
    db: AsyncSession,
    user_id: str,
    plan: str,
    ls_customer_id: str | None = None,
    ls_subscription_id: str | None = None,
    subscription_status: str | None = None,
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        return

    user.plan = plan
    user.daily_limit = (
        settings.pro_alerts_per_day if plan == "pro" else settings.free_alerts_per_day
    )
    if ls_customer_id:
        user.ls_customer_id = ls_customer_id
    if ls_subscription_id:
        user.ls_subscription_id = ls_subscription_id
    if subscription_status:
        user.subscription_status = subscription_status
    await db.commit()
