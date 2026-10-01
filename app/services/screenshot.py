from playwright.async_api import async_playwright, Browser, Playwright
import asyncio
import logging
import time
from urllib.parse import urlencode

from app.config import settings

logger = logging.getLogger(__name__)

# Module-level browser reference (initialized at startup)
_playwright: Playwright | None = None
_browser: Browser | None = None
_semaphore: asyncio.Semaphore | None = None


BROWSER_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    # Several chart tabs render at once; don't let Chromium throttle
    # the ones in the background (it left charts blank)
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
]

# One chart capture may not take longer than this, whatever hangs
CAPTURE_TIMEOUT_S = 60
# page.evaluate has no built-in timeout
EVAL_TIMEOUT_S = 10

_browser_lock: asyncio.Lock | None = None


async def start_browser():
    """Call once at app startup."""
    global _playwright, _browser, _semaphore, _browser_lock
    _semaphore = asyncio.Semaphore(settings.screenshot_concurrency)
    _browser_lock = asyncio.Lock()
    _playwright = await async_playwright().__aenter__()
    _browser = await _playwright.chromium.launch(headless=True, args=BROWSER_ARGS)
    logger.info("Playwright browser started (concurrency=%d)", settings.screenshot_concurrency)


async def _ensure_browser():
    """Relaunch Chromium if it crashed, instead of failing every screenshot until a redeploy."""
    global _browser
    if _browser and _browser.is_connected():
        return
    async with _browser_lock:
        if _browser and _browser.is_connected():
            return
        logger.warning("Browser not connected, relaunching")
        try:
            if _browser:
                await _browser.close()
        except Exception:
            pass
        _browser = await _playwright.chromium.launch(headless=True, args=BROWSER_ARGS)


async def stop_browser():
    """Call at app shutdown."""
    global _browser, _playwright
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("Playwright browser stopped")


def build_chart_url(
    symbol: str,
    interval: str | None = None,
    layout_id: str | None = None,
) -> str:
    """
    TradingView chart URL. A layout_id loads the user's saved layout
    (indicators, drawings, style); the layout must have sharing enabled.
    """
    base = "https://www.tradingview.com/chart/"
    if layout_id:
        base += f"{layout_id}/"
    params = {"symbol": symbol}
    if interval:
        params["interval"] = interval
    return f"{base}?{urlencode(params)}"


CHART_SELECTOR = "[data-qa-id='chart-container']"
PANE_SELECTOR = "canvas[data-name='pane-canvas']"

HIDE_OVERLAYS_CSS = """
    .legend-l31H9iuA, .container-SXMXfs_Z, .paneControls-JQv8nO8e,
    .control-bar-wrapper, .tv-spinner, .tv-floating-toolbar,
    .overlap-manager, #overlap-manager-root, .tv-dialog-container,
    .tv-dialog, .toast-container, div[id^="sp_message_container"],
    .cookie-banner, #cookies-settings-bubble {
        display: none !important;
    }
"""

# True once the main chart canvas has candles drawn on it. Downscales each
# pane canvas to 200x100 and counts pixels that differ from the background.
CHART_DRAWN_JS = """() => {
    const probe = document.createElement('canvas');
    probe.width = 200; probe.height = 100;
    const pctx = probe.getContext('2d', { willReadFrequently: true });
    for (const c of document.querySelectorAll("canvas[data-name='pane-canvas']")) {
        if (c.width < 300 || c.height < 200) continue;
        pctx.clearRect(0, 0, 200, 100);
        pctx.drawImage(c, 0, 0, 200, 100);
        const d = pctx.getImageData(0, 0, 200, 100).data;
        const [r0, g0, b0] = [d[0], d[1], d[2]];
        let ink = 0;
        for (let i = 0; i < d.length; i += 4) {
            if (d[i + 3] > 0 && Math.abs(d[i] - r0) + Math.abs(d[i + 1] - g0) + Math.abs(d[i + 2] - b0) > 60) ink++;
        }
        if (ink > 300) return true;
    }
    return false;
}"""

ZOOM_JS = """() => {
    // Click zoom-in 3 times for a clear view without being "too big"
    const zoomBtn = document.querySelector('[class*="control-bar__btn--zoom-in"]');
    if (!zoomBtn) return 'zoom button not found';
    for (let i = 0; i < 3; i++) {
        zoomBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    }
    return 'clicked 3 times';
}"""


async def take_screenshot(
    symbol: str,
    interval: str | None = None,
    layout_id: str | None = None,
) -> bytes | None:
    """
    Returns PNG bytes or None on failure.
    Uses semaphore to enforce strict concurrency limit.
    Tries twice with a fresh browser context; the second try drops the
    exchange prefix if there is one.
    """
    if not _playwright or not _semaphore:
        logger.error("Browser not initialized")
        return None

    async with _semaphore:
        # Second try: without the exchange prefix (a wrong exchange guess
        # gives an empty chart), otherwise the same symbol again
        bare = symbol.split(":", 1)[1] if ":" in symbol else symbol
        for attempt, candidate in enumerate((symbol, bare), start=1):
            started = time.monotonic()
            try:
                await _ensure_browser()
                png = await asyncio.wait_for(
                    _capture(candidate, interval, layout_id), timeout=CAPTURE_TIMEOUT_S
                )
            except SymbolNotFound:
                logger.info("Symbol %s not found on TradingView", candidate)
                continue
            except Exception as e:
                logger.warning(
                    "Screenshot attempt %d failed for %s after %.1fs: %s",
                    attempt, candidate, time.monotonic() - started, e or type(e).__name__,
                )
                continue
            logger.info(
                "Screenshot ok for %s in %.1fs (attempt %d)",
                candidate, time.monotonic() - started, attempt,
            )
            return png

        logger.error("Screenshot failed for %s after 2 attempts", symbol)
        return None


class SymbolNotFound(Exception):
    pass


async def _evaluate(page, js: str):
    return await asyncio.wait_for(page.evaluate(js), timeout=EVAL_TIMEOUT_S)


async def _capture(symbol: str, interval: str | None, layout_id: str | None) -> bytes:
    context = await _browser.new_context(
        viewport={"width": 1920, "height": 1080},
        device_scale_factor=1.5,  # sharp in Discord, lighter than 2x
    )
    try:
        page = await context.new_page()
        # Don't wait for "networkidle": a live chart streams data forever,
        # so that wait often ran into its timeout. Wait for the chart itself.
        await page.goto(
            build_chart_url(symbol, interval, layout_id),
            timeout=settings.playwright_timeout_ms,
            wait_until="domcontentloaded",
        )
        # Hide toolbars before the chart draws. Hiding them afterwards resized
        # the chart, which wiped the canvas just before the screenshot.
        await page.add_style_tag(content=HIDE_OVERLAYS_CSS)

        try:
            await page.wait_for_selector(PANE_SELECTOR, timeout=settings.playwright_timeout_ms)
        except Exception:
            text = (await _evaluate(page, "() => document.body ? document.body.innerText : ''")).lower()
            if "doesn't exist" in text or "invalid symbol" in text:
                raise SymbolNotFound(symbol)
            raise

        if not layout_id:  # custom layouts keep their own zoom
            try:
                await _evaluate(page, ZOOM_JS)
            except Exception as e:
                logger.warning("Could not zoom for %s: %s", symbol, e)

        # The canvas exists before the price data arrives; wait for candles,
        # let the last ones and the price axis finish, then confirm again
        await page.wait_for_function(CHART_DRAWN_JS, timeout=15000, polling=500)
        await page.wait_for_timeout(settings.screenshot_wait_ms)
        await page.wait_for_function(CHART_DRAWN_JS, timeout=5000, polling=250)

        try:
            return await page.locator(CHART_SELECTOR).screenshot(type="png", timeout=5000)
        except Exception as e:
            logger.warning("Element screenshot failed for %s, using full page: %s", symbol, e)
            return await page.screenshot(type="png", full_page=False, timeout=5000)
    finally:
        try:
            await asyncio.wait_for(context.close(), timeout=EVAL_TIMEOUT_S)
        except Exception:
            pass
