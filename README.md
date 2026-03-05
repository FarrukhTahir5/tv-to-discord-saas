# ChartAlert — TradingView → Discord Alert SaaS

Auto-forward TradingView alerts to Discord with live chart screenshots.

## Architecture

```
TradingView Alert → POST /webhook/{token} → Queue → Screenshot → Discord
```

**Two services in production:**
- **API** (`RUN_MODE=api`) — Handles HTTP requests, webhook ingestion, dashboard
- **Worker** (`RUN_MODE=worker`) — Background job processing, Playwright screenshots, Discord posting

## Quick Start (Local Dev)

```bash
# 1. Copy env file and fill in your secrets
cp .env.example .env

# 2. Start everything with Docker Compose
docker compose up --build

# 3. Visit http://localhost:8000
```

## Without Docker

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Set up Postgres and update DATABASE_URL in .env

# 3. Run migrations
alembic upgrade head

# 4. Start the app (combined mode)
RUN_MODE=both uvicorn app.main:app --reload
```

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | PostgreSQL connection string |
| `SECRET_KEY` | ✅ | JWT signing key (random 256-bit) |
| `STRIPE_SECRET_KEY` | For billing | Stripe API secret key |
| `STRIPE_WEBHOOK_SECRET` | For billing | Stripe webhook signing secret |
| `STRIPE_PRICE_ID_MONTHLY` | For billing | Stripe price ID for monthly plan |
| `REDIS_URL` | Optional | Upstash Redis URL (for production queue) |
| `RUN_MODE` | Optional | `api`, `worker`, or `both` (default: `both`) |
| `SCREENSHOT_CONCURRENCY` | Optional | Max concurrent screenshots (default: `2`) |

## Production Deployment

1. **API service**: Deploy with `RUN_MODE=api` — no browser needed
2. **Worker service**: Deploy with `RUN_MODE=worker` — needs Playwright Dockerfile
3. **Database**: Supabase PostgreSQL
4. **Redis**: Upstash (optional, for persistent queue when traffic grows)

## Running Tests

```bash
pytest tests/ -v
```
