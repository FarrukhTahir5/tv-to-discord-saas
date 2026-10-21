from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str

    # App
    secret_key: str
    app_name: str = "ChartAlert"
    app_url: str = "http://localhost:8000"
    admin_email: str = "farrukhtahir5@gmail.com"

    # LemonSqueezy
    lemonsqueezy_api_key: str = ""
    lemonsqueezy_webhook_secret: str = ""
    lemonsqueezy_store_id: str = ""
    lemonsqueezy_variant_id_monthly: str = ""
    lemonsqueezy_variant_id_yearly: str = ""

    # Plans
    free_alerts_per_day: int = 10
    pro_alerts_per_day: int = 500

    # Playwright
    playwright_timeout_ms: int = 20000
    screenshot_wait_ms: int = 1500
    screenshot_concurrency: int = 2

    # Admin panel checks the worker's browser through this URL (api mode)
    worker_health_url: str = "http://worker:8001/health/playwright"

    # Outreach emails (sent by the worker). Nothing sends until the SMTP login
    # and a postal address (required by US CAN-SPAM) are set.
    outreach_smtp_host: str = "smtp.gmail.com"
    outreach_smtp_port: int = 587
    outreach_imap_host: str = "imap.gmail.com"
    outreach_email: str = ""            # the Gmail address that sends
    outreach_app_password: str = ""     # Gmail app password (not your normal password)
    outreach_from_name: str = "Farrukh from ChartAlert"
    outreach_postal_address: str = ""
    outreach_daily_limit: int = 15      # first emails + follow-ups per day
    outreach_followup_days: int = 5
    outreach_api_token: str = ""        # lets the daily research agent add leads

    # Redis (optional)
    redis_url: Optional[str] = None

    # Run mode: "api" | "worker" | "both"
    run_mode: str = "both"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
