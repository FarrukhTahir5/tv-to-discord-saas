import re
import uuid
import datetime

from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import get_db
from app.models import AlertLog, User, UserWebhook
from app.services.auth import get_current_user

from app.config import settings

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["dashboard"])

DISCORD_WEBHOOK_PATTERN = re.compile(
    r"^https://discord\.com/api/webhooks/\d{17,20}/[\w-]{60,70}$"
)


@router.get("/dashboard")
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Recent 20 alerts for this user
    result = await db.execute(
        select(AlertLog)
        .where(AlertLog.user_id == user.id)
        .order_by(AlertLog.created_at.desc())
        .limit(20)
    )
    recent_alerts = result.scalars().all()

    # User webhooks
    wh_result = await db.execute(

        select(UserWebhook).where(UserWebhook.user_id == user.id).order_by(UserWebhook.created_at.desc())
    )
    user_webhooks = wh_result.scalars().all()

    webhook_url = f"{settings.app_url}/webhook/{user.webhook_token}"
    alert_limit = user.effective_daily_limit

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "user_webhooks": user_webhooks,
            "webhook_url": webhook_url,
            "recent_alerts": recent_alerts,
            "alert_limit": alert_limit,
            "app_name": settings.app_name,
            "title": "Dashboard",
        },
    )



@router.post("/dashboard/settings")
async def update_settings(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    discord_url = form.get("discord_webhook_url", "").strip()
    default_exchange = form.get("default_exchange", "NASDAQ").strip().upper()
    default_symbol = form.get("default_symbol", "").strip() or None

    # Validate Discord URL
    if discord_url and not DISCORD_WEBHOOK_PATTERN.match(discord_url):
        raise HTTPException(400, "Invalid Discord webhook URL")

    # Update user via a fresh query
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.discord_webhook_url = discord_url
    db_user.default_exchange = default_exchange
    db_user.default_symbol = default_symbol
    await db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/dashboard/rotate-token")
async def rotate_token(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    db_user.webhook_token = str(uuid.uuid4())
    db_user.webhook_token_created_at = datetime.datetime.utcnow()
    await db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)
@router.post("/dashboard/webhooks/add")
async def add_webhook(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    name = form.get("name", "Alert Channel").strip()
    url = form.get("url", "").strip()

    if not url or not DISCORD_WEBHOOK_PATTERN.match(url):
        raise HTTPException(400, "Invalid Discord webhook URL")

    new_wh = UserWebhook(user_id=user.id, name=name, url=url)
    db.add(new_wh)

    await db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/dashboard/webhooks/{webhook_id}/delete")
async def delete_webhook(
    webhook_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UserWebhook).where(UserWebhook.id == webhook_id, UserWebhook.user_id == user.id)
    )

    wh = result.scalar_one_or_none()
    if not wh:
        raise HTTPException(404, "Webhook not found")

    await db.delete(wh)
    await db.commit()

    return RedirectResponse(url="/dashboard", status_code=303)
