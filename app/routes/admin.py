from datetime import datetime, time, timedelta

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from app.db import get_db
from app.models import User, AlertLog

from app.services.auth import get_current_user
from app.config import settings
from app.templates_config import templates

router = APIRouter(prefix="/admin", tags=["admin"])


def admin_required(user: User = Depends(get_current_user)):
    if user.email != "farrukhtahir5@gmail.com":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@router.get("/")
async def admin_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    now = datetime.utcnow()
    today_start = datetime.combine(now.date(), time.min)

    # Basic stats
    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    pro_users = (
        await db.execute(select(func.count(User.id)).where(User.plan == "pro"))
    ).scalar()
    free_users = total_users - pro_users
    total_alerts = (await db.execute(select(func.count(AlertLog.id)))).scalar()
    today_alerts = (
        await db.execute(
            select(func.count(AlertLog.id)).where(AlertLog.created_at >= today_start)
        )
    ).scalar()

    # Subscription stats
    paid_pro = (
        await db.execute(
            select(func.count(User.id)).where(
                and_(User.plan == "pro", User.ls_subscription_id.isnot(None))
            )
        )
    ).scalar()

    on_trial = (
        await db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.plan == "free",
                    User.trial_expires_at.isnot(None),
                    User.trial_expires_at > now,
                )
            )
        )
    ).scalar()

    expiring_soon = (
        await db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.trial_expires_at.isnot(None),
                    User.trial_expires_at > now,
                    User.trial_expires_at <= now + timedelta(days=7),
                )
            )
        )
    ).scalar()

    churned = (
        await db.execute(
            select(func.count(User.id)).where(
                and_(
                    User.plan == "free",
                    User.subscription_status == "inactive",
                    User.ls_subscription_id.isnot(None),
                )
            )
        )
    ).scalar()

    # Recent users
    users = (
        await db.execute(select(User).order_by(User.created_at.desc()).limit(100))
    ).scalars().all()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": admin,
            "total_users": total_users,
            "pro_users": pro_users,
            "free_users": free_users,
            "total_alerts": total_alerts,
            "today_alerts": today_alerts,
            "paid_pro": paid_pro,
            "on_trial": on_trial,
            "expiring_soon": expiring_soon,
            "churned": churned,
            "users": users,
            "now": now,
            "title": "Admin Dashboard",
        },
    )
