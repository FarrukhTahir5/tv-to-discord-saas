# Project Context: ChartAlert

## Architecture Overview
ChartAlert is a Python-based SaaS application built with **FastAPI**. It follows a decoupled architecture designed for scalability and reliability, separating request handling from heavy background processing.

### Multi-Service Design
The application is designed to run in different modes (`RUN_MODE`):
- **API Mode (`api`)**: Handles user authentication, dashboard UI, billing integrations, and webhook ingestion.
- **Worker Mode (`worker`)**: Processes the background queue, performs chart screenshots using Playwright, and handles Discord delivery.
- **Combined Mode (`both`)**: Runs both API and Worker in a single process (default for local development).

## Tech Stack
- **Backend Framework**: FastAPI (Asynchronous Python)
- **Database**: PostgreSQL with SQLAlchemy (asyncio)
- **Migrations**: Alembic
- **Task Queue**: In-memory queue for dev, Redis-backed for production
- **Screenshot Engine**: Playwright (Headless Chromium)
- **Billing**: LemonSqueezy (recently migrated from Stripe/Gumroad)
- **Containerization**: Docker & Docker Compose
- **Logging**: Structlog for structured JSON logging

## Core Components

### 1. Webhook Ingestion (`app/routes/webhook.py`)
Receives `POST` requests from TradingView. It validates the user's `webhook_token`, checks daily limits, and queues the alert for processing.

### 2. Screenshot Service (`app/services/screenshot_svc.py`)
The heart of the "Worker". It navigates to TradingView charts, handles the "Buy/Sell" visualization, and captures the screenshot. It uses a concurrency-limited pool of browser instances.

### 3. Discord Integration (`app/services/discord_svc.py`)
Handles the delivery of alerts and screenshots to Discord via webhooks. Supports multi-webhook routing per user.

### 4. Billing & Subscription (`app/routes/billing.py`)
Integrates with LemonSqueezy to handle checkouts and webhooks for subscription management (Pro vs. Free plans).

### 5. Trial System (`app/models/user.py`)
A custom trial system that grants "Pro" access for a one-week period (`trial_expires_at`).

## Repository Structure
- `app/`: Core application code.
    - `models/`: Database schemas (User, Alert, UserWebhook).
    - `routes/`: API endpoints (Auth, Dashboard, Billing, Webhook).
    - `services/`: Specialized logic (Screenshot, Queue, Discord, LemonSqueezy).
    - `static/` & `templates/`: HTML/CSS for the user dashboard.
- `alembic/`: Database migration history.
- `scripts/`: Operational scripts (e.g., granting trials, database cleanup).
- `tests/`: Pytest suite for API and service validation.
- `Dockerfile` & `docker-compose.yml`: Infrastructure as code.

## Current Project State
- **Billing**: Successfully migrated to LemonSqueezy.
- **Features**: Multi-webhook support and Trial system are fully implemented.
- **Reliability**: Queue system ensures that momentary bursts in TradingView alerts don't overwhelm the screenshot service.
- **Deployment Ready**: Configured for VPS deployment using Docker and Caddy for SSL termination.
