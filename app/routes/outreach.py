import datetime
import hmac
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.models import OutreachLead, User
from app.routes.admin import admin_required
from app.services import outreach
from app.templates_config import templates

router = APIRouter(tags=["outreach"])

STATUSES = ["new", "sent", "followed_up", "replied", "signed_up", "unsubscribed", "bounced", "skipped"]


def _check_token(request: Request):
    expected = settings.outreach_api_token
    given = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(403, "Invalid outreach token")  # 401 would redirect to /login


# ------------------------------------------------------------------
# API for the daily research agent
# ------------------------------------------------------------------
@router.post("/api/outreach/leads")
async def api_add_leads(request: Request, db: AsyncSession = Depends(get_db)):
    _check_token(request)
    payload = await request.json()
    items = payload.get("leads") if isinstance(payload, dict) else None
    if not isinstance(items, list) or len(items) > 100:
        raise HTTPException(400, 'Send {"leads": [...]} with at most 100 leads')
    return await outreach.add_leads(db, items)


@router.get("/api/outreach/known")
async def api_known(request: Request, db: AsyncSession = Depends(get_db)):
    """Communities and business domains already in the list, so research skips them."""
    _check_token(request)
    rows = (await db.execute(select(OutreachLead.community, OutreachLead.email))).all()
    domains = sorted({
        outreach.lead_domain(e) for _, e in rows
        if outreach.lead_domain(e) not in outreach.FREE_MAIL_DOMAINS
    })
    return {"communities": sorted({c for c, _ in rows}), "domains": domains}


# ------------------------------------------------------------------
# Unsubscribe (link in every email + one-click header)
# ------------------------------------------------------------------
async def _unsubscribe(token: str, db: AsyncSession) -> bool:
    lead = (await db.execute(
        select(OutreachLead).where(OutreachLead.unsubscribe_token == token)
    )).scalar_one_or_none()
    if not lead:
        return False
    if lead.status != "signed_up":
        lead.status = "unsubscribed"
        await db.commit()
    return True


@router.get("/u/{token}", response_class=HTMLResponse)
async def unsubscribe_page(token: str, db: AsyncSession = Depends(get_db)):
    found = await _unsubscribe(token, db)
    text = "You're unsubscribed. You won't get any more emails from ChartAlert." if found \
        else "This unsubscribe link isn't valid, but you won't be emailed again from this address."
    return HTMLResponse(
        "<!doctype html><meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Unsubscribed</title>"
        "<body style='font-family:system-ui,sans-serif;background:#0b0f19;color:#e5e7eb;"
        "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0;padding:16px'>"
        f"<p style='max-width:420px;text-align:center;line-height:1.5'>{text}</p></body>"
    )


@router.post("/u/{token}")
async def unsubscribe_one_click(token: str, db: AsyncSession = Depends(get_db)):
    await _unsubscribe(token, db)
    return {"unsubscribed": True}


# ------------------------------------------------------------------
# Admin page
# ------------------------------------------------------------------
def _back(**params) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    return RedirectResponse(url=f"/admin/outreach{query}", status_code=303)


@router.get("/admin/outreach")
async def admin_outreach(
    request: Request,
    status: str = "",
    msg: str = "",
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    now = datetime.datetime.utcnow()
    counts = dict((await db.execute(
        select(OutreachLead.status, func.count(OutreachLead.id)).group_by(OutreachLead.status)
    )).all())
    contacted = sum(counts.get(s, 0) for s in ("sent", "followed_up", "replied", "signed_up", "unsubscribed", "bounced"))

    query = select(OutreachLead).order_by(OutreachLead.created_at.desc()).limit(300)
    if status in STATUSES:
        query = query.where(OutreachLead.status == status)
    leads = (await db.execute(query)).scalars().all()

    return templates.TemplateResponse(
        "admin_outreach.html",
        {
            "request": request,
            "user": admin,
            "leads": leads,
            "counts": counts,
            "contacted": contacted,
            "sent_today": await outreach.sent_today(db, now),
            "daily_limit": settings.outreach_daily_limit,
            "paused": await outreach.is_paused(db),
            "configured": outreach.is_configured(),
            "missing": [
                name for name, value in (
                    ("OUTREACH_EMAIL", settings.outreach_email),
                    ("OUTREACH_APP_PASSWORD", settings.outreach_app_password),
                    ("OUTREACH_POSTAL_ADDRESS", settings.outreach_postal_address),
                    ("OUTREACH_API_TOKEN", settings.outreach_api_token),
                ) if not value
            ],
            "in_window": outreach.in_send_window(now),
            "statuses": STATUSES,
            "active_status": status,
            "msg": msg,
            "title": "Outreach",
        },
    )


@router.post("/admin/outreach/pause")
async def admin_outreach_pause(db: AsyncSession = Depends(get_db), admin: User = Depends(admin_required)):
    await outreach.set_paused(db, True)
    return _back(msg="Outreach paused. No emails will be sent.")


@router.post("/admin/outreach/resume")
async def admin_outreach_resume(db: AsyncSession = Depends(get_db), admin: User = Depends(admin_required)):
    await outreach.set_paused(db, False)
    return _back(msg="Outreach resumed.")


@router.post("/admin/outreach/test-email")
async def admin_outreach_test(admin: User = Depends(admin_required)):
    if not (settings.outreach_email and settings.outreach_app_password):
        return _back(msg="Set OUTREACH_EMAIL and OUTREACH_APP_PASSWORD first.")
    try:
        await outreach.send_test_email()
    except Exception as e:
        return _back(msg=f"Test email failed: {e}")
    return _back(msg=f"Test email sent to {settings.outreach_email}. Check that inbox.")


@router.post("/admin/outreach/leads/{lead_id}/status")
async def admin_outreach_set_status(
    lead_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(admin_required),
):
    form = await request.form()
    new_status = form.get("status")
    if new_status not in STATUSES:
        raise HTTPException(400, "Invalid status")
    lead = await db.get(OutreachLead, lead_id)
    if not lead:
        raise HTTPException(404, "Lead not found")
    lead.status = new_status
    if new_status == "replied" and not lead.replied_at:
        lead.replied_at = datetime.datetime.utcnow()
    await db.commit()
    return _back(msg=f"{lead.email} marked {new_status.replace('_', ' ')}")
