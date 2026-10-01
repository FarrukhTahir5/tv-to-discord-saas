# Setup in 2 minutes

## 1. Connect Discord (30 sec)
In Discord: **Channel settings → Integrations → Webhooks → New Webhook → Copy Webhook URL**.
Paste it in the ChartAlert dashboard under **Connect Discord**.

## 2. Send a test (10 sec)
Click **Send test alert**. A BTC chart appears in your Discord channel.

## 3. Add to TradingView (1 min)
Create an alert (**Alt + A**), then:
- **Notifications** tab: tick **Webhook URL** and paste your ChartAlert webhook URL.
- **Message** box: paste this exact message:

```
{{exchange}}:{{ticker}} tf={{interval}} Price {{close}}
```

- Click **Create**.

TradingView fills in the symbol and timeframe, so every alert gets the right chart.

## Optional
- **Your own indicators:** turn on sharing for a TradingView chart layout and paste its link under Preferences.
- **Extra text:** add anything after the message, e.g. `... Price {{close}} Breakout above resistance`.
