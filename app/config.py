from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str

    # App
    secret_key: str
    app_name: str = "ChartAlert"
    app_url: str = "http://localhost:8000"

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_id_monthly: str = ""
    stripe_price_id_yearly: str = ""

    # Plans
    free_alerts_per_day: int = 10
    pro_alerts_per_day: int = 500

    # Playwright
    playwright_timeout_ms: int = 15000
    screenshot_wait_ms: int = 4000
    screenshot_concurrency: int = 2

    # Redis (optional)
    redis_url: Optional[str] = None

    # Run mode: "api" | "worker" | "both"
    run_mode: str = "both"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
