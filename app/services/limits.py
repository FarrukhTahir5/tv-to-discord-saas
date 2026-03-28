from sqlalchemy import select
from app.db import AsyncSessionLocal
from app.models.user import User
from app.config import settings
import datetime


async def check_and_increment_usage(user_id: str) -> bool:
    """
    Returns True if user is within limit and increments counter.
    Returns False if limit exceeded.
    Resets counter if it's a new day.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            return False

        today = datetime.date.today()

        # Reset counter if new day
        if user.alerts_reset_at != today:
            user.alerts_used_today = 0
            user.alerts_reset_at = today

        # Check limit based on plan
        limit = user.effective_daily_limit

        if user.alerts_used_today >= limit:
            await db.commit()
            return False

        user.alerts_used_today += 1
        await db.commit()
        return True
