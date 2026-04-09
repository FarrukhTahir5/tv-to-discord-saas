"""
LemonSqueezy billing service — create checkout sessions + verify webhooks.
Docs: https://docs.lemonsqueezy.com/api
"""

import hmac
import hashlib
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
