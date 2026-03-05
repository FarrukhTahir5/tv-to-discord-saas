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
