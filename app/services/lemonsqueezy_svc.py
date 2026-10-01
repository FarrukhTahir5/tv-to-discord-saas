"""
LemonSqueezy billing service — create checkout sessions + verify webhooks.
Docs: https://docs.lemonsqueezy.com/api
"""

import datetime
import hmac
import hashlib
from typing import Optional

import aiohttp
from app.config import settings

LS_API_BASE = "https://api.lemonsqueezy.com/v1"


async def create_checkout(
    user_id: str,
    user_email: str,
    variant_id: str,
) -> str:
    """
    Create a LemonSqueezy checkout and return the checkout URL.
    User is redirected there to complete payment.
    """
    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "custom": {
                        "user_id": user_id,
                    },
                },
                "checkout_options": {
                    "embed": False,
                },
            },
            "relationships": {
                "store": {
                    "data": {"type": "stores", "id": settings.lemonsqueezy_store_id}
                },
                "variant": {
                    "data": {"type": "variants", "id": variant_id}
                },
            },
        }
    }

    headers = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{LS_API_BASE}/checkouts",
            json=payload,
            headers=headers,
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"LemonSqueezy checkout error: {text}")

            data = await resp.json()
            return data["data"]["attributes"]["url"]


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """
    Verify LemonSqueezy webhook signature (HMAC-SHA256).
    The signature is sent in the X-Signature header.
    """
    if not signature:
        return False

    secret = settings.lemonsqueezy_webhook_secret.encode("utf-8")
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()

    return hmac.compare_digest(expected, signature)


# Subscription statuses that keep Pro access while billing continues.
# past_due: LemonSqueezy is still retrying the payment.
PRO_STATUSES = {"active", "on_trial", "past_due"}


def parse_ls_datetime(value: Optional[str]) -> Optional[datetime.datetime]:
    """Parse LemonSqueezy ISO timestamps ("2026-10-21T10:00:00.000000Z") to naive UTC."""
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo:
        dt = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return dt


def apply_subscription(user, attrs: dict, subscription_id: str = "") -> str:
    """
    Update a user from a LemonSqueezy subscription's attributes (webhook or API).
    Cancelled subscriptions keep Pro until ends_at — the customer already paid
    for that period. Does not commit. Returns the subscription status applied.
    """
    status = attrs.get("status", "")
    customer_id = str(attrs.get("customer_id") or "")

    if status in PRO_STATUSES:
        user.plan = "pro"
        user.subscription_status = status
        user.subscription_ends_at = None
        user.subscription_renews_at = parse_ls_datetime(attrs.get("renews_at"))
    elif status == "cancelled":
        user.plan = "pro"
        user.subscription_status = "cancelled"
        # No end date shouldn't happen, but if it does treat access as ended now
        user.subscription_ends_at = (
            parse_ls_datetime(attrs.get("ends_at")) or datetime.datetime.utcnow()
        )
        user.subscription_renews_at = None
    else:  # expired, unpaid, paused
        user.plan = "free"
        user.subscription_status = "inactive"
        user.subscription_ends_at = None
        user.subscription_renews_at = None

    if customer_id:
        user.ls_customer_id = customer_id
    if subscription_id:
        user.ls_subscription_id = subscription_id
    user.daily_limit = (
        settings.pro_alerts_per_day if user.plan == "pro" else settings.free_alerts_per_day
    )
    return status


async def get_subscription(subscription_id: str) -> dict:
    """Fetch a subscription's attributes from the LemonSqueezy API."""
    headers = {
        "Accept": "application/vnd.api+json",
        "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{LS_API_BASE}/subscriptions/{subscription_id}",
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"LemonSqueezy API error {resp.status}: {text[:200]}")
            data = await resp.json()
            return data["data"]["attributes"]
