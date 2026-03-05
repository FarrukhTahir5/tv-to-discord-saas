from sqlalchemy import String, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
import uuid
import datetime


class AlertLog(Base):
    __tablename__ = "alerts_log"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(
        String, unique=True, index=True
    )

    # Raw + parsed
    raw_text: Mapped[str] = mapped_column(String)
    parsed_symbol: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    parsed_message: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    # Status tracking
    # Values: queued | screenshot_ok | discord_ok | failed
    status: Mapped[str] = mapped_column(String, default="queued")
    # Values: parse | screenshot | discord | billing | timeout
    error_stage: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    # Metrics
    processing_time_ms: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    discord_status_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    request_ip: Mapped[str | None] = mapped_column(
        String, nullable=True
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now()
    )
