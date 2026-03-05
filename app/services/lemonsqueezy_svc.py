"""
LemonSqueezy billing service — thin wrapper around the LS REST API.
Docs: https://docs.lemonsqueezy.com/api
"""

import aiohttp
from app.config import settings

LS_API = "https://api.lemonsqueezy.com/v1"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


async def create_checkout(user_id: str, user_email: str, variant_id: str | None = None) -> str:
    """
    Create a LemonSqueezy checkout and return the hosted checkout URL.
    We pass user_id + email as custom_data so the webhook can link
    the subscription back to our user record.
    """
    vid = variant_id or settings.lemonsqueezy_variant_id_monthly

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "email": user_email,
                    "custom": {"user_id": user_id},
                },
                "product_options": {
                    "redirect_url": f"{settings.app_url}/dashboard?upgraded=true",
                },
            },
            "relationships": {
                "store": {
                    "data": {"type": "stores", "id": settings.lemonsqueezy_store_id}
                },
                "variant": {
                    "data": {"type": "variants", "id": vid}
                },
            },
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{LS_API}/checkouts", json=payload, headers=_headers()
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["data"]["attributes"]["url"]
