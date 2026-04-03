from app.services.parser import parse_alert, _build_symbol

def test_exchange_detection():
    test_cases = [
        # (raw_text, default_exchange, expected_symbol)
        ("AAPL is breaking out", "NASDAQ", "NASDAQ:AAPL"),
        ("BTCUSD looks bullish", "NASDAQ", "BTCUSD"),  # Should NOT prepend NASDAQ to BTCUSD
        ("SPY crossing level", "NASDAQ", "AMEX:SPY"),  # Should detect AMEX for SPY
        ("SPX hit target", "NASDAQ", "CBOE:SPX"),      # Should detect CBOE for SPX
        ("BINANCE:ETHUSDT", "NASDAQ", "BINANCE:ETHUSDT"), # Should stay as is
        ("TSLA", "AUTO", "TSLA"),                      # AUTO should return just ticker
    ]

    for text, default, expected in test_cases:
        parsed = parse_alert(text, default_exchange=default)
        print(f"Text: '{text}' | Default: {default} | Result: {parsed.symbol} | Expected: {expected}")
        assert parsed.symbol == expected

if __name__ == "__main__":
    try:
        test_exchange_detection()
        print("\nAll tests passed!")
    except AssertionError as e:
        print("\nTest failed!")
