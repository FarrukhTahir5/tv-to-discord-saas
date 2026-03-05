from sqlalchemy import String, DateTime, Integer, Boolean, Date, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
import uuid
import datetime


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)

    # Webhook
    webhook_token: Mapped[str] = mapped_column(
        String, unique=True, index=True, default=lambda: str(uuid.uuid4())
    )
    webhook_token_created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now()
    )

    # Discord
    discord_webhook_url: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    # Alert defaults
    default_exchange: Mapped[str] = mapped_column(String, default="NASDAQ")
    default_symbol: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    timezone: Mapped[str] = mapped_column(String, default="UTC")

    # Usage limits
    daily_limit: Mapped[int] = mapped_column(Integer, default=10)
    alerts_used_today: Mapped[int] = mapped_column(Integer, default=0)
    alerts_reset_at: Mapped[datetime.date | None] = mapped_column(
        Date, nullable=True
    )

    # Billing
    plan: Mapped[str] = mapped_column(String, default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    subscription_status: Mapped[str] = mapped_column(
        String, default="inactive"
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
