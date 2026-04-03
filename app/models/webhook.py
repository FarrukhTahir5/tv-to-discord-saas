from sqlalchemy import String, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base
import uuid
import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .user import User

class UserWebhook(Base):
    __tablename__ = "user_webhooks"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), default="Primary Channel")
    url: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="webhooks")
