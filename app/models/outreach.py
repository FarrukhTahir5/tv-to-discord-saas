from sqlalchemy import String, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
import uuid
import secrets
import datetime


class OutreachLead(Base):
    """A trading community contacted by the automated outreach emails."""

    __tablename__ = "outreach_leads"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String, nullable=True)        # person's first name, if known
    community: Mapped[str] = mapped_column(String)                         # e.g. "Big Picture Swing Trading"
    niche: Mapped[str | None] = mapped_column(String, nullable=True)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)  # where the lead was found
    hook: Mapped[str | None] = mapped_column(Text, nullable=True)          # personal first line
    country: Mapped[str | None] = mapped_column(String, nullable=True)

    # new -> sent -> followed_up, or replied / unsubscribed / bounced / signed_up / skipped
    status: Mapped[str] = mapped_column(String, default="new", index=True)
    sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    followed_up_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    replied_at: Mapped[datetime.datetime | None] = mapped_column(DateTime, nullable=True)
    message_id: Mapped[str | None] = mapped_column(String, nullable=True)  # for threading the follow-up
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    unsubscribe_token: Mapped[str] = mapped_column(
        String, unique=True, default=lambda: secrets.token_urlsafe(24)
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime, default=func.now())


class AppSetting(Base):
    """Small key/value store for switches changed from the admin panel."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String)
