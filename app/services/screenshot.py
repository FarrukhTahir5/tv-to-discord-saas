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
                viewport={"width": 1920, "height": 1080},
                device_scale_factor=2,  # Retina quality
            )
            page = await context.new_page()

            # Navigate with timeout
            await page.goto(
                url,
                timeout=settings.playwright_timeout_ms,
                wait_until="networkidle",  # Wait for more stability
            )

            # Wait for chart to render and hide potential overlays
            try:
                # Target the central chart area
                chart_selector = ".layout__area--center"
                await page.wait_for_selector(chart_selector, timeout=12000)
                
                # Hide sidebars, toolbars, and cookie banners to let chart expand
                await page.add_style_tag(content="""
                    /* Hide surrounding UI components */
                    .layout__area--top,
                    .layout__area--left,
                    .layout__area--right,
                    .layout__area--bottom,
                    .header-chart-panel,
                    .footer-chart-panel,
                    .tv-side-toolbar,
                    #drawing-toolbar,
                    .widgetbar-wrap,
                    .chart-controls-bar,
                    .tv-floating-toolbar,
                    .anchor-3Y_mXp_m,
                    div[id^="sp_message_container"],
                    .cookie-banner,
                    #cookies-settings-bubble,
                    .overlap-manager,
                    #overlap-manager-root,
                    .tv-dialog-container,
                    .tv-dialog,
                    .toast-container,
                    .closeButton-zLVm6B4t { 
                        display: none !important; 
                    }

                    /* Expand the central chart to full viewport */
                    .layout__area--center {
                        inset: 0 !important;
                        width: 100% !important;
                        height: 100% !important;
                    }
                """)
                
                # Give it a moment to reflow
                await page.wait_for_timeout(1000)
                
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
