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
    
    plan_id = (
        settings.nowpayments_plan_id_yearly 
        if plan_type == "yearly" 
        else settings.nowpayments_plan_id_monthly
    )

    try:
        sub_id = await create_email_subscription(user.email, plan_id)
        
        # Update user with sub_id
        user.np_subscriber_id = str(sub_id)
        await db.commit()
        
        return RedirectResponse(url="/dashboard?upgraded=pending", status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


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
