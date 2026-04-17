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

            try:
                chart_selector = "[data-qa-id='chart-container']"
                await page.wait_for_selector(chart_selector, timeout=12000)
                await page.wait_for_selector(
                    "canvas[data-name='pane-canvas']", timeout=10000
                )
                await page.wait_for_timeout(2000)

                # Step 1: Click 1D time range via JS
                try:
                    result = await page.evaluate("""() => {
                        const btn = document.querySelector(
                            'button[data-name="date-range-tab-1D"]'
                        );
                        if (btn) { btn.click(); return 'clicked'; }
                        return 'not found';
                    }""")
                    logger.info("screenshot %s: 1D range button => %s", symbol, result)
                    await page.wait_for_timeout(2000)
                except Exception as e:
                    logger.warning("Could not set 1D range for %s: %s", symbol, e)

                # Step 2: Force daily interval via JS dropdown
                try:
                    result = await page.evaluate("""() => {
                        const btns = document.querySelectorAll(
                            'button[class*="menuBtn"]'
                        );
                        let opened = false;
                        for (const btn of btns) {
                            if (btn.offsetParent !== null) {
                                btn.click();
                                opened = true;
                                break;
                            }
                        }
                        return opened ? 'dropdown opened' : 'no visible menuBtn';
                    }""")
                    logger.info("screenshot %s: interval dropdown => %s", symbol, result)
                    await page.wait_for_timeout(500)
                    result2 = await page.evaluate("""() => {
                        const item = document.querySelector('[data-value="1D"]');
                        if (item) { item.click(); return '1D clicked'; }
                        return '1D not found';
                    }""")
                    logger.info("screenshot %s: set daily => %s", symbol, result2)
                    await page.wait_for_timeout(3000)
                except Exception as e:
                    logger.warning("Could not set daily interval for %s: %s", symbol, e)

                # Step 3: Zoom in 15 times via JS click on zoom button
                try:
                    zoom_result = await page.evaluate("""() => {
                        // Make control bar visible
                        const bars = document.querySelectorAll(
                            '[class*="control-bar"]'
                        );
                        for (const bar of bars) {
                            if (bar.classList.contains(
                                'control-bar--hidden'
                            )) {
                                bar.classList.remove(
                                    'control-bar--hidden'
                                );
                            }
                            bar.style.display = '';
                            bar.style.visibility = 'visible';
                            bar.style.opacity = '1';
                        }
                        // Click zoom-in 15 times
                        const zoomBtn = document.querySelector(
                            '[class*="control-bar__btn--zoom-in"]'
                        );
                        if (!zoomBtn) return 'zoom button not found';
                        for (let i = 0; i < 5; i++) {
                            zoomBtn.dispatchEvent(
                                new MouseEvent('click', {
                                    bubbles: true,
                                    cancelable: true,
                                })
                            );
                        }
                        return 'clicked 5 times';
                    }""")
                    logger.info("screenshot %s: zoom => %s", symbol, zoom_result)
                    await page.wait_for_timeout(3000)
                except Exception as e:
                    logger.warning("Could not zoom for %s: %s", symbol, e)

                # Step 4: Hide overlays
                await page.add_style_tag(content="""
                    .legend-l31H9iuA, .container-SXMXfs_Z, .paneControls-JQv8nO8e,
                    .control-bar-wrapper, .tv-spinner, .tv-floating-toolbar,
                    .overlap-manager, #overlap-manager-root, .tv-dialog-container,
                    .tv-dialog, .toast-container, div[id^="sp_message_container"],
                    .cookie-banner, #cookies-settings-bubble {
                        display: none !important;
                    }
                """)
                await page.wait_for_timeout(500)

                chart_element = page.locator(chart_selector)
                screenshot = await chart_element.screenshot(
                    type="png", timeout=5000,
                )
                return screenshot
            except Exception as e:
                logger.warning("Selector-based screenshot failed for %s, falling back: %s", symbol, e)
                await page.wait_for_timeout(settings.screenshot_wait_ms)
                screenshot = await page.screenshot(type="png", full_page=False)
                return screenshot

        except Exception as e:
            logger.error("Screenshot failed for %s: %s", symbol, e)
            return None

        finally:
            if context:
                await context.close()
