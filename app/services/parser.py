import re
from dataclasses import dataclass
from typing import Optional


TICKER_REGEX = re.compile(r"\b([A-Z]{1,5}(?:[.\-][A-Z0-9]{1,4})?)\b")

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
        r"\b([A-Z_]+:[A-Z0-9]{1,10})\b", raw_text.upper()
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
        if 1 <= len(candidate) <= 10:
            ticker = candidate
            message = parts[1].strip()
            symbol = _build_symbol(ticker, default_exchange)
            return ParsedAlert(
                ticker=ticker,
                symbol=symbol,
                message=message,
                source="comma",
            )

    # Layer 3: Regex find all-caps word 2-6 chars
    upper_text = raw_text.upper()
    matches = re.findall(r"\b([A-Z]{2,6})\b", upper_text)
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


def _build_symbol(ticker: str, exchange: str) -> str:
    ticker = ticker.strip().upper()
    exchange = exchange.strip().upper()
    if ":" in ticker:
        return ticker  # already fully qualified
    return f"{exchange}:{ticker}"
