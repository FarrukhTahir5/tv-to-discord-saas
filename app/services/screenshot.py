from playwright.async_api import async_playwright, Browser, Playwright
import asyncio
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level browser reference (initialized at startup)
_playwright: Playwright | None = None
_browser: Browser | None = None
_semaphore: asyncio.Semaphore | None = None


async def start_browser():
    """Call once at app startup."""
    global _playwright, _browser, _semaphore
    _semaphore = asyncio.Semaphore(settings.screenshot_concurrency)
    _playwright = await async_playwright().__aenter__()
    _browser = await _playwright.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
        ],
    )
    logger.info("Playwright browser started (concurrency=%d)", settings.screenshot_concurrency)


async def stop_browser():
    """Call at app shutdown."""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.__aexit__(None, None, None)
        _playwright = None
    logger.info("Playwright browser stopped")


async def take_screenshot(symbol: str) -> bytes | None:
    """
    Returns PNG bytes or None on failure.
    Uses semaphore to enforce strict concurrency limit.
    """
    if not _browser or not _semaphore:
        logger.error("Browser not initialized")
        return None

    url = f"https://www.tradingview.com/chart/?symbol={symbol}"

    async with _semaphore:
        context = None
        try:
            context = await _browser.new_context(
                viewport={"width": 1400, "height": 800},
                device_scale_factor=2,  # Retina quality
            )
            page = await context.new_page()

            # Navigate with timeout
            await page.goto(
                url,
                timeout=settings.playwright_timeout_ms,
                wait_until="domcontentloaded",
            )

            # Wait for chart to render
            try:
                await page.wait_for_selector(
                    ".chart-container", timeout=5000
                )
            except Exception:
                await page.wait_for_timeout(settings.screenshot_wait_ms)

            screenshot = await page.screenshot(
                type="png",
                full_page=False,
                timeout=5000,
            )
            return screenshot

        except Exception as e:
            logger.error("Screenshot failed for %s: %s", symbol, e)
            return None

        finally:
            if context:
                await context.close()  # ALWAYS close to prevent memory leaks
