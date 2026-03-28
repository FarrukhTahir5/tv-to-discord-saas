"""
NowPayments billing service — thin wrapper around the NP REST API for Recurring Payments.
Docs: https://documenter.getpostman.com/view/7907941/2s93JusNJt#api-documentation
"""

import aiohttp
import hmac
import hashlib
import json
from app.config import settings

NP_API_BASE = "https://api.nowpayments.io/v1"


async def _get_auth_token() -> str:
    """
    Authenticate with NowPayments and return the JWT token.
    Required for some Recurring Payments endpoints.
    """
    payload = {
        "email": settings.nowpayments_email,
        "password": settings.nowpayments_password,
    }
    
    headers = {
        "Content-Type": "application/json",
        "x-api-key": settings.nowpayments_api_key,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{NP_API_BASE}/auth", 
            json=payload, 
            headers=headers
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"NowPayments Auth Error: {text}")
            
            data = await resp.json()
            return data.get("token")


async def create_email_subscription(email_addr: str, plan_id: str) -> str:
    """
    Create a recurring payment subscription by email.
    NowPayments will send an email invoice to the user.
    """
    # Documentation fix: The field must be 'email', not 'subscriber_email'.
    payload = {
        "subscription_plan_id": int(plan_id),
        "email": email_addr,
    }

    # Some endpoints work with x-api-key, others need Bearer JWT.
    # We provide BOTH to be safe, as NP can be picky.
    token = await _get_auth_token()

    headers = {
        "x-api-key": settings.nowpayments_api_key,
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession() as session:
        # POST /v1/subscriptions
        async with session.post(
            f"{NP_API_BASE}/subscriptions", 
            json=payload, 
            headers=headers
        ) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise Exception(f"NowPayments API Error: {text}")
            
            data = await resp.json()
            return data.get("id") or "created"


def verify_ipn_signature(payload_dict: dict, signature: str) -> bool:
    """
    Verify NowPayments IPN signature (HMAC-SHA512).
    According to docs, we must sort the keys alphabetically.
    """
    if not signature:
        return False
    
    # NP IPN Verification Logic:
    # 1. Sort keys
    sorted_payload = dict(sorted(payload_dict.items()))
    
    # 2. Stringify (separators ensures no extra spaces)
    payload_str = json.dumps(sorted_payload, separators=(',', ':'))
    
    secret = settings.nowpayments_ipn_secret.encode("utf-8")
    expected = hmac.new(secret, payload_str.encode("utf-8"), hashlib.sha512).hexdigest()
    
    return hmac.compare_digest(expected, signature)
