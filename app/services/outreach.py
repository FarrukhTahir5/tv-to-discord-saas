"""
Automated outreach emails to trading communities.

Runs inside the worker process:
  - every minute, during US business hours on weekdays, sends at most one
    email (first contact or the single follow-up), spaced several minutes
    apart and capped at OUTREACH_DAILY_LIMIT per day
  - every 30 minutes, checks the Gmail inbox for replies and bounces so
    those leads never get a follow-up

Leads are added by the daily research agent through the outreach API.
Every email carries an unsubscribe link, a List-Unsubscribe header and the
sender's postal address (US CAN-SPAM). EU/EEA/UK/Swiss leads are skipped.
"""

import asyncio
import datetime
import email.utils
import imaplib
import logging
import random
import re
import smtplib
from email.message import EmailMessage
from typing import Optional

from sqlalchemy import select, func, or_

from app.config import settings
from app.db import AsyncSessionLocal
from app.models import OutreachLead, AppSetting, User

logger = logging.getLogger(__name__)

PAUSED_KEY = "outreach_paused"
SUBJECT = "charts on your Discord alerts"

# Weekdays, 14:00-21:00 UTC = 10am-5pm US Eastern
SEND_DAYS = range(0, 5)
SEND_HOURS = range(14, 21)
MIN_GAP_MIN, MAX_GAP_MIN = 6, 14
REPLY_CHECK_EVERY_S = 30 * 60

# Cold email to these needs prior consent (GDPR / PECR / Swiss law)
BLOCKED_COUNTRIES = {
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU",
    "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES",
    "SE", "IS", "LI", "NO", "GB", "UK", "CH",
}
BLOCKED_TLDS = {c.lower() for c in BLOCKED_COUNTRIES} | {"eu"}
FREE_MAIL_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "aol.com", "proton.me", "protonmail.com", "live.com",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.IGNORECASE)

_task: Optional[asyncio.Task] = None
_next_send_at: Optional[datetime.datetime] = None
_last_reply_check: Optional[datetime.datetime] = None


# ---- Rules ----------------------------------------------------------

def is_configured() -> bool:
    return bool(
        settings.outreach_email
        and settings.outreach_app_password
        and settings.outreach_postal_address
    )


def rejection_reason(email_addr: str, country: Optional[str]) -> Optional[str]:
    """Why a lead can't be emailed, or None if it can."""
    if not email_addr or not EMAIL_RE.match(email_addr):
        return "invalid email"
    if country and country.strip().upper() in BLOCKED_COUNTRIES:
        return f"country {country.upper()} not allowed"
    tld = email_addr.rsplit(".", 1)[-1].lower()
    if tld in BLOCKED_TLDS:
        return f".{tld} address not allowed"
    return None


def in_send_window(now: datetime.datetime) -> bool:
    return now.weekday() in SEND_DAYS and now.hour in SEND_HOURS


def unsubscribe_url(lead: OutreachLead) -> str:
    return f"{settings.app_url}/u/{lead.unsubscribe_token}"


# ---- Message text ---------------------------------------------------

def _signature() -> str:
    return settings.outreach_from_name.split()[0] if settings.outreach_from_name else "Farrukh"


def _footer(lead: OutreachLead) -> str:
    return (
        "\n--\n"
        f"{settings.outreach_postal_address}\n"
        f"Not interested? One click and you won't hear from me again: {unsubscribe_url(lead)}\n"
    )


def compose(lead: OutreachLead, followup: bool = False) -> tuple[str, str]:
    """Plain-text subject and body. Plain text lands in the inbox more often than HTML."""
    hello = f"Hi {lead.name}," if lead.name else "Hi there,"
    page = f"{settings.app_url}/tradingview-alerts-to-discord"
    if followup:
        body = (
            f"{hello}\n\n"
            "Just bumping this in case it got buried. I'm still happy to set ChartAlert up on "
            f"{lead.community}'s Discord free for 2 weeks. If it's not a fit, no worries, "
            "I won't follow up again.\n\n"
            f"{_signature()}\n"
        )
        return f"Re: {SUBJECT}", body + _footer(lead)

    hook = f"{lead.hook.strip()}\n\n" if lead.hook and lead.hook.strip() else ""
    body = (
        f"{hello}\n\n"
        f"{hook}"
        "Quick question: when you post alerts in your Discord, do members get the chart, "
        "or just the text?\n\n"
        "I built ChartAlert, which adds the live TradingView chart to every alert "
        "automatically. You keep writing alerts the way you do now. Here's what a post "
        f"looks like: {page}\n\n"
        "If you want, I'll set it up on your server free for 2 weeks. It takes about 2 minutes.\n\n"
        f"{_signature()}\n"
        "ChartAlert\n"
    )
    return SUBJECT, body + _footer(lead)


# ---- SMTP / IMAP (blocking, run in a thread) --------------------------

def _send_blocking(to: str, subject: str, body: str, unsub_url: str,
                   in_reply_to: Optional[str] = None) -> str:
    msg = EmailMessage()
    sender = settings.outreach_email
    msg["From"] = email.utils.formataddr((settings.outreach_from_name, sender))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=False)
    msg_id = email.utils.make_msgid(domain=sender.split("@")[-1])
    msg["Message-ID"] = msg_id
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    # One-click unsubscribe in Gmail/Yahoo's UI
    msg["List-Unsubscribe"] = f"<{unsub_url}>, <mailto:{sender}?subject=unsubscribe>"
    msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(body)

    with smtplib.SMTP(settings.outreach_smtp_host, settings.outreach_smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(sender, settings.outreach_app_password)
        smtp.send_message(msg)
    return msg_id


def _check_inbox_blocking(leads: list[tuple[str, datetime.datetime]]) -> dict[str, str]:
    """Returns {email: "replied" | "bounced"} for leads that answered or bounced."""
    found: dict[str, str] = {}
    imap = imaplib.IMAP4_SSL(settings.outreach_imap_host)
    try:
        imap.login(settings.outreach_email, settings.outreach_app_password)
        imap.select("INBOX", readonly=True)
        for addr, since in leads:
            since_str = since.strftime("%d-%b-%Y")
            status, data = imap.search(None, "FROM", f'"{addr}"', "SINCE", since_str)
            if status == "OK" and data and data[0].split():
                found[addr] = "replied"
                continue
            status, data = imap.search(None, "FROM", '"mailer-daemon"', "SINCE", since_str, "BODY", f'"{addr}"')
            if status == "OK" and data and data[0].split():
                found[addr] = "bounced"
    finally:
        try:
            imap.logout()
        except Exception:
            pass
    return found


# ---- Pause switch ----------------------------------------------------

async def is_paused(db) -> bool:
    row = await db.get(AppSetting, PAUSED_KEY)
    return bool(row and row.value == "1")


async def set_paused(db, paused: bool):
    row = await db.get(AppSetting, PAUSED_KEY)
    if row:
        row.value = "1" if paused else "0"
    else:
        db.add(AppSetting(key=PAUSED_KEY, value="1" if paused else "0"))
    await db.commit()


# ---- Sending ---------------------------------------------------------

async def sent_today(db, now: datetime.datetime) -> int:
    start = datetime.datetime.combine(now.date(), datetime.time.min)
    firsts = (await db.execute(
        select(func.count(OutreachLead.id)).where(OutreachLead.sent_at >= start)
    )).scalar()
    followups = (await db.execute(
        select(func.count(OutreachLead.id)).where(OutreachLead.followed_up_at >= start)
    )).scalar()
    return firsts + followups


async def _next_lead(db, now: datetime.datetime) -> tuple[Optional[OutreachLead], bool]:
    """Due follow-ups go first, then the oldest new lead. Returns (lead, is_followup)."""
    due = now - datetime.timedelta(days=settings.outreach_followup_days)
    lead = (await db.execute(
        select(OutreachLead)
        .where(OutreachLead.status == "sent", OutreachLead.sent_at <= due)
        .order_by(OutreachLead.sent_at.asc()).limit(1)
    )).scalar_one_or_none()
    if lead:
        return lead, True
    lead = (await db.execute(
        select(OutreachLead)
        .where(OutreachLead.status == "new")
        .order_by(OutreachLead.created_at.asc()).limit(1)
    )).scalar_one_or_none()
    return lead, False


async def send_one(now: Optional[datetime.datetime] = None) -> Optional[str]:
    """Send the next due email. Returns the address emailed, or None."""
    now = now or datetime.datetime.utcnow()
    async with AsyncSessionLocal() as db:
        if await is_paused(db):
            return None
        if await sent_today(db, now) >= settings.outreach_daily_limit:
            return None
        lead, followup = await _next_lead(db, now)
        if not lead:
            return None

        # Re-check right before sending: rules may have changed since the lead was added
        reason = rejection_reason(lead.email, lead.country)
        is_customer = (await db.execute(
            select(User.id).where(func.lower(User.email) == lead.email.lower())
        )).first()
        if reason or is_customer:
            lead.status = "signed_up" if is_customer else "skipped"
            lead.last_error = reason
            await db.commit()
            return None

        subject, body = compose(lead, followup)
        try:
            msg_id = await asyncio.to_thread(
                _send_blocking, lead.email, subject, body, unsubscribe_url(lead),
                lead.message_id if followup else None,
            )
        except smtplib.SMTPRecipientsRefused as e:
            lead.status, lead.last_error = "bounced", str(e)[:300]
            await db.commit()
            return None
        except Exception as e:
            # Login/network problems: leave the lead as is and try again later
            lead.last_error = str(e)[:300]
            await db.commit()
            logger.error("Outreach send to %s failed: %s", lead.email, e)
            raise

        if followup:
            lead.status, lead.followed_up_at = "followed_up", now
        else:
            lead.status, lead.sent_at, lead.message_id = "sent", now, msg_id
        lead.last_error = None
        await db.commit()
        logger.info("Outreach %s sent to %s (%s)", "follow-up" if followup else "email", lead.email, lead.community)
        return lead.email


async def check_replies(now: Optional[datetime.datetime] = None) -> int:
    """Mark leads that replied or bounced so they never get a follow-up."""
    now = now or datetime.datetime.utcnow()
    async with AsyncSessionLocal() as db:
        leads = (await db.execute(
            select(OutreachLead).where(OutreachLead.status.in_(("sent", "followed_up")))
        )).scalars().all()
        if not leads:
            return 0
        found = await asyncio.to_thread(
            _check_inbox_blocking,
            [(l.email, l.sent_at or now) for l in leads],
        )
        for l in leads:
            if l.email in found:
                l.status = found[l.email]
                if l.status == "replied":
                    l.replied_at = now
        await db.commit()
        if found:
            logger.info("Outreach inbox check: %s", found)
        return len(found)


async def send_test_email() -> str:
    """Send the first-contact email to the sending address itself, to check the setup."""
    lead = OutreachLead(
        email=settings.outreach_email, name="Farrukh", community="Your Community",
        hook="(Personal first line goes here, e.g. something they posted.)",
        unsubscribe_token="test",
    )
    subject, body = compose(lead)
    return await asyncio.to_thread(
        _send_blocking, settings.outreach_email, f"[TEST] {subject}", body, unsubscribe_url(lead)
    )


# ---- Loop ------------------------------------------------------------

async def _loop():
    global _next_send_at, _last_reply_check
    while True:
        try:
            now = datetime.datetime.utcnow()
            if is_configured():
                if not _last_reply_check or (now - _last_reply_check).total_seconds() >= REPLY_CHECK_EVERY_S:
                    _last_reply_check = now
                    await check_replies(now)
                if in_send_window(now) and (not _next_send_at or now >= _next_send_at):
                    if await send_one(now):
                        _next_send_at = now + datetime.timedelta(
                            minutes=random.uniform(MIN_GAP_MIN, MAX_GAP_MIN)
                        )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Outreach loop error: %s", e, exc_info=True)
            _next_send_at = datetime.datetime.utcnow() + datetime.timedelta(minutes=30)
        await asyncio.sleep(60)


def start_outreach():
    global _task
    _task = asyncio.create_task(_loop())
    logger.info("Outreach loop started (configured=%s)", is_configured())


async def stop_outreach():
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass


def lead_domain(email_addr: str) -> str:
    return email_addr.rsplit("@", 1)[-1].lower()


async def add_leads(db, items: list[dict]) -> dict:
    """Validate and insert leads from the research agent. Never re-adds a known address or business domain."""
    added, skipped = 0, []
    for item in items:
        addr = (item.get("email") or "").strip().lower()
        community = (item.get("community") or "").strip()
        country = (item.get("country") or "").strip() or None
        reason = rejection_reason(addr, country)
        if not reason and not community:
            reason = "missing community"
        if not reason:
            dom = lead_domain(addr)
            same = select(OutreachLead.id).where(OutreachLead.email == addr)
            if dom not in FREE_MAIL_DOMAINS:
                same = select(OutreachLead.id).where(
                    or_(OutreachLead.email == addr, OutreachLead.email.like(f"%@{dom}"))
                )
            if (await db.execute(same.limit(1))).first():
                reason = "already known"
            elif (await db.execute(select(User.id).where(func.lower(User.email) == addr))).first():
                reason = "already a customer"
        if reason:
            skipped.append({"email": addr, "reason": reason})
            continue
        db.add(OutreachLead(
            email=addr,
            name=(item.get("name") or "").strip() or None,
            community=community[:200],
            niche=(item.get("niche") or "").strip() or None,
            source_url=(item.get("source_url") or "").strip() or None,
            hook=(item.get("hook") or "").strip()[:400] or None,
            country=country,
        ))
        await db.flush()
        added += 1
    await db.commit()
    return {"added": added, "skipped": skipped}
