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
from app.services.lemonsqueezy_svc import (
    apply_subscription,
    create_checkout,
    verify_webhook_signature,
)

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

    # Only subscription objects carry the subscription's status. Payment events
    # (subscription_payment_*) carry an invoice; LemonSqueezy also sends a
    # subscription_updated whenever the status changes, so those are skipped.
    if data.get("type") != "subscriptions":
        return {"received": True, "skipped": f"Ignored {event_name}"}

    user_email = attrs.get("user_email")
    customer_id = str(attrs.get("customer_id", ""))
    subscription_id = str(data.get("id", ""))

    # Try to find user by custom_data user_id, then LemonSqueezy customer, then email
    user = None
    user_id = custom_data.get("user_id")
    if user_id:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

    if not user and customer_id:
        result = await db.execute(select(User).where(User.ls_customer_id == customer_id))
        user = result.scalar_one_or_none()

    if not user and user_email:
        result = await db.execute(select(User).where(User.email == user_email))
        user = result.scalar_one_or_none()

    if not user:
        logger.warn("lemonsqueezy_webhook_user_not_found", email=user_email, user_id=user_id)
        return {"received": True, "skipped": "User not found"}

    status = apply_subscription(user, attrs, subscription_id)
    await db.commit()
    logger.info(
        "lemonsqueezy_subscription_applied",
        user_id=user.id, ls_event=event_name, status=status,
        plan=user.plan, ends_at=str(user.subscription_ends_at),
    )

    return {"received": True}
