import re
from dataclasses import dataclass
from typing import Optional


TICKER_REGEX = re.compile(r"\b([A-Z]{1,12}(?:[.\-][A-Z0-9]{1,4})?)\b")

STOP_WORDS = {
    "THE", "AND", "FOR", "WITH", "THIS", "FROM", "THAT", "WILL",
    "HIGH", "LOW", "HAS", "WAS", "ARE", "BUT", "NOT", "YOU",
    "ALL", "CAN", "HER", "WAS", "ONE", "OUR", "OUT", "BUY",
    "SELL", "LONG", "SHORT", "ABOVE", "BELOW",
    "ALERT", "PRICE", "OPEN", "CLOSE", "MARKET", "BROKE",
    "CROSS", "JUST", "SIDE", "LIKE", "ALSO", "WENT",
    "OFF", "SET", "RUN", "GOT", "GET", "PUT", "HIT", "NEW",
    "UP", "AT", "TO", "ON", "IN", "OR", "IF", "SO", "DO",
    "BY", "NO", "GO", "IT", "IS", "BE", "AS", "AN", "OF",
    "VALUE", "CROSSING", "CROSSES", "ENTER", "EXIT",
}


@dataclass
class ParsedAlert:
    ticker: Optional[str]   # Raw ticker e.g. "CHEF"
    symbol: Optional[str]   # Full symbol e.g. "NASDAQ:CHEF"
    message: str             # Remaining text
    source: str              # How ticker was found: "explicit|comma|regex|default|none"


def parse_alert(
    raw_text: str,
    default_exchange: str = "NASDAQ",
    default_symbol: Optional[str] = None,
) -> ParsedAlert:
    raw_text = raw_text.strip()

    # Layer 1: Explicit EXCHANGE:TICKER format
    explicit_match = re.search(
        r"\b([A-Z_]+:[A-Z0-9]{1,12})\b", raw_text.upper()
    )
    if explicit_match:
        symbol = explicit_match.group(1)
        ticker = symbol.split(":")[1]
        message = raw_text.replace(explicit_match.group(), "").strip()
        return ParsedAlert(
            ticker=ticker,
            symbol=symbol,
            message=message or raw_text,
            source="explicit",
        )

    # Layer 2: Comma-separated first token
    if "," in raw_text:
        parts = raw_text.split(",", 1)
        candidate = parts[0].strip().upper()
        candidate = re.sub(r"[^A-Z0-9.\-]", "", candidate)
        if 1 <= len(candidate) <= 12:
            ticker = candidate
            message = parts[1].strip()
            symbol = _build_symbol(ticker, default_exchange)
            return ParsedAlert(
                ticker=ticker,
                symbol=symbol,
                message=message,
                source="comma",
            )

    # Layer 3: Regex find all-caps word 2-12 chars
    upper_text = raw_text.upper()
    matches = re.findall(r"\b([A-Z]{2,12})\b", upper_text)
    candidates = [m for m in matches if m not in STOP_WORDS]
    if candidates:
        ticker = candidates[0]
        symbol = _build_symbol(ticker, default_exchange)
        return ParsedAlert(
            ticker=ticker,
            symbol=symbol,
            message=raw_text,
            source="regex",
        )


    # Layer 4: Fallback to user's default_symbol
    if default_symbol:
        return ParsedAlert(
            ticker=None,
            symbol=default_symbol,
            message=raw_text,
            source="default",
        )

    # Layer 5: Give up gracefully
    return ParsedAlert(
        ticker=None,
        symbol=None,
        message=raw_text,
        source="none",
    )


def detect_exchange(ticker: str) -> Optional[str]:
    """
    Heuristically detect the exchange for a given ticker.
    Returns None if uncertain, letting TradingView resolve it.
    """
    ticker = ticker.strip().upper()

    # 1. Crypto Pairs (BTCUSD, ETHUSDT, etc.)
    if any(suffix in ticker for suffix in ["USD", "USDT", "USDC", "EUR", "GBP", "JPY", "KRW"]):
        # TradingView's default (e.g. BITSTAMP or BINANCE) is usually correct
        return None

    # 2. Major US Indices
    indices = {
        "SPX": "CBOE",
        "SPX500": "FX_IDC",
        "NDX": "NASDAQ",
        "NAS100": "FX_IDC",
        "DJI": "DJI",
        "US30": "FX_IDC",
        "VIX": "CBOE",
        "DXY": "TVC",
        "USDT.D": "CRYPTOCAP",
        "BTC.D": "CRYPTOCAP",
    }
    if ticker in indices:
        return indices[ticker]

    # 3. Global Indices
    global_indices = {
        "DAX": "XETR",
        "DE30": "FX_IDC",
        "FTSE": "INDEX",
        "UK100": "FX_IDC",
        "NIFTY": "NSE",
        "BANKNIFTY": "NSE",
        "SENSEX": "BSE",
        "TSX": "TSX",
        "ASX": "ASX",
    }
    if ticker in global_indices:
        return global_indices[ticker]

    # 4. Major US ETFs (mostly AMEX/NYSE Arca)
    etfs = {"SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "VXX", "UVXY", "ARKK"}
    if ticker in etfs:
        return "AMEX"

    # 5. Forex Pairs (6 chars, e.g. EURUSD)
    if len(ticker) == 6 and any(cur in ticker for cur in ["EUR", "USD", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]):
        return "FX_IDC"

    # Default to None to let TradingView's search engine find the best match
    return None


def _build_symbol(ticker: str, default_exchange: str) -> str:
    ticker = ticker.strip().upper()
    if ":" in ticker:
        return ticker  # already fully qualified

    # 1. Try heuristic detection first
    detected = detect_exchange(ticker)
    if detected:
        return f"{detected}:{ticker}"

    # 2. High-confidence Crypto check (even if not in detect_exchange list)
    # If it ends in USDT/USDC, it's 99% crypto. Don't prepend a stock exchange.
    if ticker.endswith(("USDT", "USDC", "BUSD", "DAI")):
        return ticker

    # 3. Handle "AUTO" or empty default
    if not default_exchange or default_exchange.upper() == "AUTO":
        return ticker

    # 4. Final fallback to user's default (e.g. "NASDAQ")
    # But skip if ticker looks like it might be crypto to avoid "NASDAQ:BTC"
    if any(c in ticker for c in ["USD", "USDT"]) and default_exchange.upper() in ["NASDAQ", "NYSE", "AMEX"]:
        return ticker

    return f"{default_exchange}:{ticker}"


