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
        await _playwright.stop()
        _playwright = None
    logger.info("Playwright browser stopped")


async def take_screenshot(symbol: str) -> bytes | None:
    """
    Returns PNG bytes or None on failure.
    Uses semaphore to enforce strict concurrency limit.
    If the symbol has an exchange prefix and TradingView shows
    "doesn't exist", retries with just the ticker (no prefix).
    """
    if not _browser or not _semaphore:
        logger.error("Browser not initialized")
        return None

    async with _semaphore:
        context = None
        try:
            context = await _browser.new_context(
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,  # Retina quality
            )
            page = await context.new_page()

            url = f"https://www.tradingview.com/chart/?symbol={symbol}"

            # Navigate with timeout
            await page.goto(
                url,
                timeout=settings.playwright_timeout_ms,
                wait_until="networkidle",
            )

            # Check if TradingView shows "This symbol doesn't exist"
            # If so, retry without the exchange prefix
            page_text = await page.inner_text("body")
            if "doesn't exist" in page_text.lower() and ":" in symbol:
                ticker = symbol.split(":", 1)[1]
                logger.info("Symbol %s not found, retrying with %s", symbol, ticker)
                url = f"https://www.tradingview.com/chart/?symbol={ticker}"
                await page.goto(
                    url,
                    timeout=settings.playwright_timeout_ms,
                    wait_until="networkidle",
                )

            # Wait for chart to render and hide potential overlays
            try:
                # Target the chart container element directly
                chart_selector = "[data-qa-id='chart-container']"
                await page.wait_for_selector(chart_selector, timeout=12000)

                # Wait for chart canvas to be painted (not just empty/loading)
                await page.wait_for_selector(
                    "canvas[data-name='pane-canvas']", timeout=10000
                )

                # Brief pause for chart data to render on canvas
                await page.wait_for_timeout(2000)

                # Hide overlays (legend, buy/sell buttons, control bars)
                # but keep the chart canvas and axes intact
                await page.add_style_tag(content="""
                    /* Legend with OHLC values */
                    .legend-l31H9iuA,
                    /* Buy/Sell buttons */
                    .container-SXMXfs_Z,
                    /* Pane control buttons */
                    .paneControls-JQv8nO8e,
                    /* Bottom control bar (zoom, scroll) */
                    .control-bar-wrapper,
                    /* Loading spinner */
                    .tv-spinner,
                    /* Floating toolbars */
                    .tv-floating-toolbar,
                    .overlap-manager,
                    #overlap-manager-root,
                    .tv-dialog-container,
                    .tv-dialog,
                    .toast-container,
                    /* Cookie banners */
                    div[id^="sp_message_container"],
                    .cookie-banner,
                    #cookies-settings-bubble {
                        display: none !important;
                    }
                """)

                # Brief reflow after hiding elements
                await page.wait_for_timeout(500)

                chart_element = page.locator(chart_selector)
                screenshot = await chart_element.screenshot(
                    type="png",
                    timeout=5000,
                )
                return screenshot
            except Exception as e:
                logger.warning("Selector-based screenshot failed for %s, falling back: %s", symbol, e)
                # Fallback to full page if selector fails
                await page.wait_for_timeout(settings.screenshot_wait_ms)
                screenshot = await page.screenshot(type="png", full_page=False)
                return screenshot



        except Exception as e:
            logger.error("Screenshot failed for %s: %s", symbol, e)
            return None

        finally:
            if context:
                await context.close()  # ALWAYS close to prevent memory leaks
