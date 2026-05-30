# TradingView Alert Setup Guide

To ensure your TradingView alerts are correctly parsed and forwarded to Discord with accurate charts, please follow these formatting rules when setting up your alert messages.

## 1. Webhook URL
First, make sure you paste your unique Webhook URL (from your dashboard) into the "Webhook URL" field in TradingView's alert notification settings.

## 2. Alert Message Format (Crucial)
For our system to accurately detect the symbol and fetch the correct chart, we strongly encourage using one of the following formats at the beginning of your alert message:

### Format A: Exact Exchange and Ticker (Recommended)
Use the exact exchange and symbol format provided by TradingView: `EXCHANGE:TICKER`

**Examples:**
> `NASDAQ:AAPL is breaking out!`
> `BINANCE:BTCUSDT long entry triggered`

This is the most reliable method as it leaves no room for ambiguity.

### Format B: Ticker with a Comma
If you only provide the ticker symbol, immediately follow it with a comma.

**Examples:**
> `AAPL, breakout above 200`
> `BTCUSDT, crossing moving average`

Our system will reliably extract everything before the comma as the symbol.

## Why is this important?
If you write `Apple is going up` or `AAPL moving fast` without the comma or exact exchange format, the parser attempts to guess the ticker using keyword matching. While it works most of the time, it can occasionally result in the wrong chart or a failure to detect the symbol entirely. 

By using `EXCHANGE:TICKER` or `TICKER,`, you guarantee 100% accuracy for your alert charts.
