from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.db import get_db
from app.models.user import User
from app.models.alert import AlertLog
from app.services.auth import get_current_user
from app.config import settings
from app.main import templates

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
    # 1. Total Users
    total_users_res = await db.execute(select(func.count(User.id)))
    total_users = total_users_res.scalar()

    # 2. Pro Users
    pro_users_res = await db.execute(select(func.count(User.id)).where(User.plan == "pro"))
    pro_users = pro_users_res.scalar()

    # 3. Free Users
    free_users = total_users - pro_users

    # 4. Total Alerts (all time)
    total_alerts_res = await db.execute(select(func.count(AlertLog.id)))
    total_alerts = total_alerts_res.scalar()

    # 5. Alerts Today
    from datetime import datetime, time
    today_start = datetime.combine(datetime.utcnow().date(), time.min)
    today_alerts_res = await db.execute(
        select(func.count(AlertLog.id)).where(AlertLog.created_at >= today_start)
    )
    today_alerts = today_alerts_res.scalar()

    # 6. Recent Users
    users_res = await db.execute(select(User).order_by(User.created_at.desc()).limit(100))
    users = users_res.scalars().all()

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
            "users": users,
            "title": "Admin Dashboard",
        },
    )
