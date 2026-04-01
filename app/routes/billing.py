"""
NowPayments billing routes — subscription creation + IPN handler.
"""

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import settings
from app.db import get_db
from app.models.user import User
from app.services.auth import get_current_user
from app.services.nowpayments_svc import create_email_subscription, verify_ipn_signature

router = APIRouter(prefix="/billing", tags=["billing"])


# ------------------------------------------------------------------
# Create subscription → NowPayments sends email to user
# ------------------------------------------------------------------
@router.post("/create-checkout")
async def billing_create_checkout(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    form = await request.form()
    plan_type = form.get("plan_type") or "monthly"
    gateway = form.get("gateway") or "gumroad"

    if gateway == "nowpayments":
        plan_id = (
            settings.nowpayments_plan_id_yearly 
            if plan_type == "yearly" 
            else settings.nowpayments_plan_id_monthly
        )

        try:
            # 3. Create NowPayments Subscription (Email flow)
            subscription_id = await create_email_subscription(user.email, plan_id)
            
            # 4. Save subscriber ID to user
            result = await db.execute(select(User).where(User.id == user.id))
            db_user = result.scalar_one()
            db_user.np_subscriber_id = subscription_id
            await db.commit()

            from app.main import templates
            return templates.TemplateResponse(
                "billing_success.html",
                {
                    "request": request,
                    "user": user,
                    "title": "Success",
                    "message": "Awesome! NowPayments has emailed you an invoice. Please pay it to activate your Pro plan."
                },
            )
        except Exception as e:
            error_msg = str(e)
            if "already subscribed" in error_msg.lower():
                from app.main import templates
                return templates.TemplateResponse(
                    "billing_success.html",
                    {
                        "request": request,
                        "user": user,
                        "title": "Already Subscribed",
                        "message": "It looks like you already have a subscription for this plan! Please check your email for the NowPayments invoice."
                    },
                )
            raise HTTPException(status_code=400, detail=error_msg)
    
    else:
        # Gumroad Redirection
        # We can append the email to pre-fill it in Gumroad
        redirect_url = f"{settings.gumroad_product_url}?email={user.email}"
        # If we have variants, we can also try to select them via URL if Gumroad supports it, 
        # but usually users select it on the page.
        return RedirectResponse(url=redirect_url, status_code=303)


# ------------------------------------------------------------------
# Gumroad Ping — update user plan
# ------------------------------------------------------------------
@router.post("/gumroad-ping")
async def gumroad_ping(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Gumroad sends form-encoded data
    form_data = await request.form()
    
    email = form_data.get("email")
    sale_id = form_data.get("sale_id")
    is_recurring = form_data.get("is_recurring") == "true"
    # variants might look like "Variant Name" or "Variant Name ($50)"
    variants = form_data.get("variants", "") 
    
    # Check if it's a cancellation/refund
    # Gumroad 'ping' doesn't have a simple 'type' field like Stripe, 
    # but it sends 'disputed' or 'refunded'.
    # Actually, for subscriptions, there's a separate ping for 'subscription_cancelled'.
    
    # Basic logic: if we get a ping, it means a sale happened or a subscription event occurred.
    # If the user is paying, they should be active.
    
    if not email:
        return {"received": True, "skipped": "No email"}

    # 3. Lookup user
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    
    if not user:
        # Maybe log this
        return {"received": True, "skipped": "User not found"}

    # Update Gumroad ID
    if sale_id:
        user.gumroad_id = str(sale_id)

    # Simple logic: if email matches, give Pro.
    # In a real app, you'd check 'subscription_cancelled' etc.
    # But for now, any ping to this endpoint from a valid sale updates the plan.
    
    # Determine plan type (optional, but good for tracking)
    # if settings.gumroad_variant_yearly in variants:
    #     ...
    
    await _set_plan(db, user, "pro", "active")

    return {"received": True}


# ------------------------------------------------------------------
# NowPayments IPN — verify signature, update user plan
# ------------------------------------------------------------------
@router.post("/nowpayments-ipn")
async def nowpayments_ipn(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # 1. Verify signature
    payload = await request.json()
    sig = request.headers.get("x-nowpayments-sig", "")
    
    if not verify_ipn_signature(payload, sig):
        raise HTTPException(400, "Invalid IPN signature")
    
    # NP IPN for subscriptions includes 'subscription_id' and 'payment_status'
    # For email subs, we also get 'customer_email' or similar usually.
    # Actually, NP IPN for recurring payments: https://nowpayments.io/documentation/recurring-payments-ipn
    
    status = payload.get("payment_status")
    sub_id = payload.get("subscription_id")
    email = payload.get("customer_email") # May vary depending on NP version, but we have sub_id

    if not sub_id and not email:
        return {"received": True, "skipped": "No identifiers found"}

    # 3. Lookup user
    query = select(User)
    if sub_id:
        query = query.where(User.np_subscriber_id == str(sub_id))
    elif email:
        query = query.where(User.email == email)
    
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    
    if not user:
        return {"received": True, "skipped": "User not found"}

    # 4. Update plan based on status
    # finished | confirmed | sending: user paid
    # failed | expired: user didn't pay
    if status in ["finished", "confirmed", "sending"]:
        await _set_plan(db, user, "pro", "active")
    elif status in ["failed", "expired"]:
        await _set_plan(db, user, "free", "inactive")

    return {"received": True}


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------
async def _set_plan(
    db: AsyncSession,
    user: User,
    plan: str,
    status: str,
):
    user.plan = plan
    user.subscription_status = status
    # Daily limit is handled by property in User model now (effective_daily_limit)
    # but we still want to keep the base column updated if possible.
    user.daily_limit = (
        settings.pro_alerts_per_day if plan == "pro" else settings.free_alerts_per_day
    )
    await db.commit()
