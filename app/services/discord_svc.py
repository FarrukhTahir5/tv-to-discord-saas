import aiohttp
import asyncio
import io
import json
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Limit concurrent Discord posts to avoid rate limits
_discord_semaphore = asyncio.Semaphore(3)


@dataclass
class DiscordResult:
    success: bool
    status_code: int
    error: str | None = None


async def post_to_discord(
    webhook_url: str,
    symbol: str,
    message: str,
    screenshot_bytes: bytes | None,
    app_name: str = "ChartAlert",
) -> DiscordResult:
    async with _discord_semaphore:
        async with aiohttp.ClientSession() as session:
            try:
                return await _do_post(
                    session, webhook_url, symbol, message,
                    screenshot_bytes, app_name,
                )
            except Exception as e:
                logger.error("Discord post exception: %s", e)
                return DiscordResult(success=False, status_code=0, error=str(e))


async def _do_post(
    session: aiohttp.ClientSession,
    webhook_url: str,
    symbol: str,
    message: str,
    screenshot_bytes: bytes | None,
    app_name: str,
) -> DiscordResult:
    # Message text appears ABOVE the embed as regular content
    content = message.strip()
    if not screenshot_bytes:
        content += "\n⚠️ *(Chart preview unavailable)*"

    # Embed is just the chart image + footer
    embed = {
        "title": symbol or "Alert",
        "color": 0x5865F2,  # Discord blurple
        "footer": {"text": f"Sent via {app_name}"},
    }

    if screenshot_bytes:
        embed["image"] = {"url": "attachment://chart.png"}

    payload = {"content": content or None, "embeds": [embed]}

    form = aiohttp.FormData()
    form.add_field(
        "payload_json",
        json.dumps(payload),
        content_type="application/json",
    )

    if screenshot_bytes:
        form.add_field(
            "files[0]",
            io.BytesIO(screenshot_bytes),
            filename="chart.png",
            content_type="image/png",
        )

    resp = await session.post(
        webhook_url,
        data=form,
        timeout=aiohttp.ClientTimeout(total=10),
    )

    # Handle Discord rate limit (429)
    if resp.status == 429:
        retry_data = await resp.json()
        wait = retry_data.get("retry_after", 1)
        logger.warning("Discord rate limited. Waiting %ss", wait)
        await asyncio.sleep(wait)

        # Rebuild form for retry (FormData is consumed after first post)
        form2 = aiohttp.FormData()
        form2.add_field(
            "payload_json",
            json.dumps(payload),
            content_type="application/json",
        )
        if screenshot_bytes:
            form2.add_field(
                "files[0]",
                io.BytesIO(screenshot_bytes),
                filename="chart.png",
                content_type="image/png",
            )
        resp = await session.post(
            webhook_url,
            data=form2,
            timeout=aiohttp.ClientTimeout(total=10),
        )

    success = resp.status in (200, 204)
    return DiscordResult(
        success=success,
        status_code=resp.status,
        error=None if success else f"HTTP {resp.status}",
    )
