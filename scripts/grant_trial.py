import asyncio
import datetime
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.db import async_session
from app.models.user import User

async def grant_trial(email: str, weeks: int = 1):
    async with async_session() as session:
        stmt = select(User).where(User.email == email)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            print(f"User with email {email} not found.")
            return

        # Set trial expiration
        user.trial_expires_at = datetime.datetime.now() + datetime.timedelta(weeks=weeks)
        
        await session.commit()
        print(f"Successfully granted {weeks}-week trial to {email}.")
        print(f"Current Time: {datetime.datetime.now()}")
        print(f"Expires at: {user.trial_expires_at}")
        print(f"Effective Plan: {user.effective_plan}")
        print(f"Effective Limit: {user.effective_daily_limit}")

if __name__ == "__main__":
    email = "bennett@bigpictureswingtrading.com"
    if len(sys.argv) > 1:
        email = sys.argv[1]
    asyncio.run(grant_trial(email))
