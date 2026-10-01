from sqlalchemy import String, DateTime, Integer, Boolean, Date, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
import uuid
import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .webhook import UserWebhook


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
    default_exchange: Mapped[str] = mapped_column(String, default="AUTO")
    default_symbol: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    timezone: Mapped[str] = mapped_column(String, default="UTC")

    # Chart appearance
    chart_layout_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    default_interval: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    # Usage limits
    daily_limit: Mapped[int] = mapped_column(Integer, default=10)
    alerts_used_today: Mapped[int] = mapped_column(Integer, default=0)
    alerts_reset_at: Mapped[datetime.date | None] = mapped_column(
        Date, nullable=True
    )

    # Billing
    plan: Mapped[str] = mapped_column(String, default="free")
    ls_customer_id: Mapped[str | None] = mapped_column(String, nullable=True)
    ls_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    subscription_status: Mapped[str] = mapped_column(String, default="inactive")
    trial_expires_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    # Set when a subscription is cancelled: Pro access continues until this time (UTC)
    subscription_ends_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    webhooks: Mapped[list["UserWebhook"]] = relationship("UserWebhook", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        from app.config import settings
        return self.email == settings.admin_email

    @property
    def on_trial(self) -> bool:
        return bool(self.trial_expires_at and self.trial_expires_at > datetime.datetime.utcnow())

    @property
    def effective_plan(self) -> str:
        """Returns 'pro' for admin, an active trial, or a paid period not yet ended."""
        if self.is_admin or self.on_trial:
            return "pro"
        if (
            self.plan == "pro"
            and self.subscription_ends_at
            and self.subscription_ends_at <= datetime.datetime.utcnow()
        ):
            return "free"
        return self.plan

    @property
    def effective_daily_limit(self) -> int:
        """Returns pro limit if effective plan is pro, otherwise free limit."""
        from app.config import settings
        return (
            settings.pro_alerts_per_day
            if self.effective_plan == "pro"
            else settings.free_alerts_per_day
        )
