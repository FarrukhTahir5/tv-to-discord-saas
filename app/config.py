from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str

    # App
    secret_key: str
    app_name: str = "ChartAlert"
    app_url: str = "http://localhost:8000"

    # NowPayments
    nowpayments_api_key: str = ""
    nowpayments_ipn_secret: str = ""
    nowpayments_email: str = ""
    nowpayments_password: str = ""
    nowpayments_plan_id_monthly: str = "1796142641"
    nowpayments_plan_id_yearly: str = "1156416554"

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
