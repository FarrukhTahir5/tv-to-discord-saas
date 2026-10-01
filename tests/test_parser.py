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

def test_message_text_does_not_change_timeframe():
    # Timeframe words in the user's own text are ignored (charts stay daily)
    assert parse_alert("CHEF, 1D Crossing Horizontal Ray").interval is None
    assert parse_alert("BTCUSDT, 15 Crossing Up EMA").interval is None
    assert parse_alert("NVDA, 900 breakout").interval is None


def test_interval_tag_is_removed_from_message():
    result = parse_alert("NASDAQ:AAPL broke out tf=4h")
    assert result.symbol == "NASDAQ:AAPL"
    assert "tf" not in result.message.lower()


def test_interval_tag_does_not_become_symbol():
    result = parse_alert("TF:15 BTCUSDT crossing up")
    assert result.ticker == "BTCUSDT"


def test_default_is_daily_even_with_tag():
    # No setting -> None, which the worker turns into the daily chart
    assert parse_alert("AAPL breakout tf=15").interval is None


def test_match_alert_setting_uses_tag():
    assert parse_alert("AAPL breakout interval=60", default_interval="alert").interval == "60"
    assert parse_alert("AAPL breakout interval=1W", default_interval="alert").interval == "W"
    assert parse_alert("AAPL breakout interval=1M", default_interval="alert").interval == "M"
    assert parse_alert("AAPL breakout tf=4h", default_interval="alert").interval == "240"
    assert parse_alert("AAPL breakout", default_interval="alert").interval is None


def test_fixed_setting_always_wins():
    assert parse_alert("AAPL breakout tf=5", default_interval="240").interval == "240"
    assert parse_alert("AAPL breakout", default_interval="W").interval == "W"


# ---- Recommended copy-paste message ---------------------------------
# {{exchange}}:{{ticker}} tf={{interval}} Price {{close}}

def test_recommended_message_format():
    result = parse_alert("NASDAQ:AAPL tf=15 Price 182.35", default_interval="alert")
    assert result.symbol == "NASDAQ:AAPL"
    assert result.interval == "15"
    assert result.message == "Price 182.35"


def test_tickers_with_special_characters():
    assert parse_alert("NYSE:BRK.B tf=D Price 410").symbol == "NYSE:BRK.B"
    assert parse_alert("CME_MINI:ES1! tf=60 Price 5000").symbol == "CME_MINI:ES1!"
    assert parse_alert("BINANCE:BTCUSDT.P tf=5 Price 65000").symbol == "BINANCE:BTCUSDT.P"


def test_trailing_period_not_part_of_symbol():
    result = parse_alert("Breakout on NASDAQ:AAPL.")
    assert result.symbol == "NASDAQ:AAPL"


def test_time_is_not_a_symbol():
    result = parse_alert("AAPL, breakout at 12:30")
    assert result.symbol != "12:30"
    assert result.ticker == "AAPL"


def test_lowercase_explicit_symbol_removed_from_message():
    result = parse_alert("nasdaq:aapl breaking out")
    assert result.symbol == "NASDAQ:AAPL"
    assert result.message == "breaking out"


def test_qqq_is_nasdaq():
    assert parse_alert("QQQ at the 727 key area").symbol == "NASDAQ:QQQ"
    assert parse_alert("SPY is testing ATH").symbol == "AMEX:SPY"
