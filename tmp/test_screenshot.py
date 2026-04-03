import asyncio
import os
from app.services.screenshot import take_screenshot, start_browser, stop_browser
from app.config import settings

async def test_screenshot():
    print("Starting browser...")
    await start_browser()
    
    symbol = "NASDAQ:AAPL"
    print(f"Taking screenshot of {symbol}...")
    screenshot_bytes = await take_screenshot(symbol)
    
    if screenshot_bytes:
        output_file = "tmp/test_chart_aapl.png"
        with open(output_file, "wb") as f:
            f.write(screenshot_bytes)
        print(f"Success! Screenshot saved to {output_file}")
    else:
        print("Failed to take screenshot.")
        
    # Test a crypto symbol without exchange
    symbol_crypto = "BTCUSD"
    print(f"Taking screenshot of {symbol_crypto}...")
    screenshot_bytes_crypto = await take_screenshot(symbol_crypto)
    
    if screenshot_bytes_crypto:
        output_file_crypto = "tmp/test_chart_btcusd.png"
        with open(output_file_crypto, "wb") as f:
            f.write(screenshot_bytes_crypto)
        print(f"Success! Crypto screenshot saved to {output_file_crypto}")
    
    await stop_browser()

if __name__ == "__main__":
    asyncio.run(test_screenshot())
