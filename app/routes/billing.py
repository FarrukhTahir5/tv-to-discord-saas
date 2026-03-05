from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import stripe

from app.config import settings
from app.db import get_db
from app.models.user import User
from app.services.auth import get_current_user

stripe.api_key = settings.stripe_secret_key
router = APIRouter(prefix="/billing", tags=["billing"])


@router.post("/create-checkout")
async def create_checkout(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    price_id = form.get("price_id", settings.stripe_price_id_monthly)

    # Get fresh user from DB
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()

    # Create or reuse Stripe customer
    if not db_user.stripe_customer_id:
        customer = stripe.Customer.create(
            email=db_user.email,
            metadata={"user_id": db_user.id},
        )
        db_user.stripe_customer_id = customer.id
        await db.commit()

    session = stripe.checkout.Session.create(
        customer=db_user.stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url=f"{settings.app_url}/dashboard?upgraded=true",
        cancel_url=f"{settings.app_url}/dashboard",
    )
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=session.url, status_code=303)


@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.stripe_webhook_secret
        )
    except Exception:
        raise HTTPException(400, "Invalid webhook signature")

    await handle_stripe_event(event, db)
    return {"received": True}


async def handle_stripe_event(event, db: AsyncSession):
    evt_type = event["type"]
    data = event["data"]["object"]

    if evt_type == "checkout.session.completed":
        customer_id = data["customer"]
        sub_id = data["subscription"]
        await set_plan(db, customer_id, "pro", sub_id, "active")

    elif evt_type == "invoice.payment_succeeded":
        customer_id = data["customer"]
        await set_plan(
            db, customer_id, "pro", subscription_status="active"
        )

    elif evt_type in (
        "invoice.payment_failed",
        "customer.subscription.deleted",
    ):
        customer_id = data.get("customer")
        await set_plan(
            db, customer_id, "free", subscription_status="inactive"
        )


async def set_plan(
    db: AsyncSession,
    customer_id: str,
    plan: str,
    sub_id: str | None = None,
    subscription_status: str | None = None,
):
    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    user.plan = plan
    user.daily_limit = (
        settings.pro_alerts_per_day
        if plan == "pro"
        else settings.free_alerts_per_day
    )
    if sub_id:
        user.stripe_subscription_id = sub_id
    if subscription_status:
        user.subscription_status = subscription_status
    await db.commit()
