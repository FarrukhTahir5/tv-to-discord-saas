import asyncio
from sqlalchemy import select
from app.db import async_session
from app.models.user import User

async def check_user():
    async with async_session() as session:
        stmt = select(User).where(User.email == "bennett@bigpictureswingtrading.com")
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        if user:
            print(f"User found: {user.email}, ID: {user.id}")
        else:
            print("User not found.")

if __name__ == "__main__":
    asyncio.run(check_user())
