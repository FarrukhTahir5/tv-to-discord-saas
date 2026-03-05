import hashlib
import bcrypt
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Request, HTTPException
from sqlalchemy import select
from app.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours


def _prep_password(password: str) -> bytes:
    """
    Pre-hash with SHA-256 so bcrypt's 72-byte limit is never hit.
    Returns bytes ready for bcrypt.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest().encode("utf-8")


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(_prep_password(password), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_prep_password(plain), hashed.encode("utf-8"))


def create_access_token(user_id: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> str | None:
    try:
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[ALGORITHM]
        )
        return payload.get("sub")
    except JWTError:
        return None


async def get_current_user(request: Request):
    """Dependency that extracts the current user from the access_token cookie."""
    from app.db import AsyncSessionLocal
    from app.models.user import User

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = decode_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user


async def get_current_user_optional(request: Request):
    """Returns user or None — for pages that work with or without auth."""
    try:
        return await get_current_user(request)
    except HTTPException:
        return None
