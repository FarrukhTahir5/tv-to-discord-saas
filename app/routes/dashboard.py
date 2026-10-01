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
from app.routes.webhook import make_idempotency_key
from app.services.queue_svc import notify_worker
from app.services.parser import MATCH_ALERT_INTERVAL
from app.services.auth import get_current_user

from app.config import settings

templates = Jinja2Templates(directory="app/templates")
router = APIRouter(tags=["dashboard"])

DISCORD_WEBHOOK_PATTERN = re.compile(
    r"^https://discord\.com/api/webhooks/\d{17,20}/[\w-]{60,70}$"
)
CHART_LAYOUT_PATTERN = re.compile(r"tradingview\.com/chart/([A-Za-z0-9]{6,12})(?:/|\?|$)")
LAYOUT_ID_PATTERN = re.compile(r"^[A-Za-z0-9]{6,12}$")

# One message works for every TradingView alert: TradingView fills in the
# placeholders, so the symbol and timeframe are always exact.
ALERT_MESSAGE_TEMPLATE = "{{exchange}}:{{ticker}} tf={{interval}} Price {{close}}"

TEST_ALERT_TEXT = "BINANCE:BTCUSDT tf=60 ChartAlert test alert: your setup works!"

# TradingView interval value -> label shown in the settings dropdown
INTERVAL_CHOICES = {
    MATCH_ALERT_INTERVAL: "Match the alert's chart",
    "1": "1 minute", "5": "5 minutes", "15": "15 minutes", "30": "30 minutes",
    "60": "1 hour", "120": "2 hours", "240": "4 hours",
    "D": "1 day", "W": "1 week", "M": "1 month",
}


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

    # Setup progress: Discord connected -> test delivered -> first real alert
    has_channel = bool(user_webhooks or user.discord_webhook_url)
    test_delivered = (
        await db.execute(
            select(AlertLog.id).where(
                AlertLog.user_id == user.id, AlertLog.status == "discord_ok"
            ).limit(1)
        )
    ).first() is not None
    has_real_alert = (
        await db.execute(
            select(AlertLog.id).where(
                AlertLog.user_id == user.id, AlertLog.raw_text != TEST_ALERT_TEXT
            ).limit(1)
        )
    ).first() is not None
    setup = {
        "channel": has_channel,
        "test": test_delivered,
        "tradingview": has_real_alert,
        "complete": has_channel and has_real_alert,
    }

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
            "interval_choices": INTERVAL_CHOICES,
            "alert_message": ALERT_MESSAGE_TEMPLATE,
            "setup": setup,
            "test_sent": request.query_params.get("test") == "sent",
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
    layout_input = form.get("chart_layout", "").strip()
    default_interval = form.get("default_interval", "").strip() or None

    # Accept a full layout URL (tradingview.com/chart/AbC123/) or the bare ID
    chart_layout_id = None
    if layout_input:
        m = CHART_LAYOUT_PATTERN.search(layout_input)
        if m:
            chart_layout_id = m.group(1)
        elif LAYOUT_ID_PATTERN.match(layout_input):
            chart_layout_id = layout_input
        else:
            raise HTTPException(400, "Invalid TradingView layout URL")

    if default_interval and default_interval not in INTERVAL_CHOICES:
        raise HTTPException(400, "Invalid default timeframe")

    # Validate Discord URL
    if discord_url and not DISCORD_WEBHOOK_PATTERN.match(discord_url):
        raise HTTPException(400, "Invalid Discord webhook URL")

    # Update user via a fresh query
    result = await db.execute(select(User).where(User.id == user.id))
    db_user = result.scalar_one()
    if "discord_webhook_url" in form:
        db_user.discord_webhook_url = discord_url
    db_user.default_exchange = default_exchange
    db_user.default_symbol = default_symbol
    db_user.chart_layout_id = chart_layout_id
    db_user.default_interval = default_interval
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
    name = form.get("name", "").strip() or "My Channel"
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


@router.post("/dashboard/test-alert")
async def send_test_alert(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Queue a sample alert through the normal pipeline (screenshot + Discord)."""
    has_channel = user.discord_webhook_url or (
        await db.execute(select(UserWebhook.id).where(UserWebhook.user_id == user.id).limit(1))
    ).first()
    if not has_channel:
        raise HTTPException(400, "Connect a Discord channel first")

    idem_key = make_idempotency_key(user.id, TEST_ALERT_TEXT)
    existing = await db.execute(select(AlertLog.id).where(AlertLog.idempotency_key == idem_key))
    if existing.first() is None:
        alert = AlertLog(
            user_id=user.id,
            idempotency_key=idem_key,
            raw_text=TEST_ALERT_TEXT,
            status="queued",
            request_ip=request.client.host if request.client else None,
        )
        db.add(alert)
        await db.commit()
        await notify_worker(alert.id)

    return RedirectResponse(url="/dashboard?test=sent", status_code=303)
