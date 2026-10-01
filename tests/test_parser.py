import pytest
from app.services.parser import parse_alert


def test_explicit_symbol():
    result = parse_alert("NASDAQ:AAPL broke out")
    assert result.symbol == "NASDAQ:AAPL"
    assert result.source == "explicit"


def test_comma_format():
    result = parse_alert("CHEF, 1D Crossing Horizontal Ray")
    assert result.ticker == "CHEF"
    assert result.message == "1D Crossing Horizontal Ray"
    assert result.source == "comma"


def test_comma_with_default_exchange():
    result = parse_alert("NVDA, breakout above 900", default_exchange="NASDAQ")
    assert result.symbol == "NASDAQ:NVDA"


def test_regex_fallback():
    result = parse_alert("CHEF breakout above resistance")
    assert result.ticker == "CHEF"
    assert result.source == "regex"


def test_default_symbol_fallback():
    result = parse_alert("breakout happening", default_symbol="NASDAQ:AAPL")
    assert result.symbol == "NASDAQ:AAPL"
    assert result.source == "default"


def test_no_ticker_found():
    result = parse_alert("alert went off")
    assert result.symbol is None
    assert result.source == "none"


def test_crypto_usdt():
    result = parse_alert("BINANCE:BTCUSDT breakout")
    assert result.symbol == "BINANCE:BTCUSDT"


def test_whitespace_cleanup():
    result = parse_alert("  AAPL ,  close above 200  ")
    assert result.ticker == "AAPL"


# ---- Timeframe / interval -------------------------------------------

def test_interval_from_tradingview_default_format():
    result = parse_alert("CHEF, 1D Crossing Horizontal Ray")
    assert result.interval == "D"
    assert result.message == "1D Crossing Horizontal Ray"


def test_interval_minutes_in_comma_format():
    result = parse_alert("BTCUSDT, 15 Crossing Up EMA")
    assert result.interval == "15"


def test_price_after_comma_is_not_interval():
    result = parse_alert("NVDA, 900 breakout")
    assert result.interval is None


def test_interval_tag_is_parsed_and_removed():
    result = parse_alert("NASDAQ:AAPL broke out tf=4h")
    assert result.symbol == "NASDAQ:AAPL"
    assert result.interval == "240"
    assert "tf" not in result.message.lower()


def test_interval_tag_does_not_become_symbol():
    result = parse_alert("TF:15 BTCUSDT crossing up")
    assert result.interval == "15"
    assert result.ticker == "BTCUSDT"


def test_interval_tag_with_tradingview_placeholder_values():
    assert parse_alert("AAPL breakout interval=60").interval == "60"
    assert parse_alert("AAPL breakout interval=1W").interval == "W"
    assert parse_alert("AAPL breakout interval=1M").interval == "M"
    assert parse_alert("AAPL breakout interval=1m").interval == "1"


def test_default_interval_fallback():
    result = parse_alert("AAPL breakout", default_interval="240")
    assert result.interval == "240"


def test_alert_interval_overrides_default():
    result = parse_alert("AAPL breakout tf=5", default_interval="D")
    assert result.interval == "5"
