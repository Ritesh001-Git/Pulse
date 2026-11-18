"""Auth: lightweight bearer tokens.

- Passwords stored as sha256 hashes (dev-grade; swap to bcrypt/argon2 before prod).
- Token = HMAC-signed "userId:expires" — stateless, no session table needed.
- AUTH can be disabled via PULSE_AUTH_ENABLED=false (default while the frontend
  has no login page) — internal endpoints then act as the seeded admin user.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import User, UserRole
from app.resilience import get_db

SECRET = get_settings().auth_secret
TOKEN_TTL_SEC = 7 * 24 * 3600


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_token(user: User) -> str:
    exp = int(time.time()) + TOKEN_TTL_SEC
    payload = f"{user.id}:{exp}"
    sig = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def _verify_token(token: str) -> uuid.UUID | None:
    try:
        user_id, exp, sig = token.rsplit(":", 2)
        payload = f"{user_id}:{exp}"
        expected = hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected) or int(exp) < time.time():
            return None
        return uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None


async def _load_user(user_id: uuid.UUID, db: AsyncSession) -> User:
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user no longer exists")
    return user


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    settings = get_settings()
    if not settings.auth_enabled:
        # Auth disabled: act as (or bootstrap) the default admin so the API
        # is fully functional while the frontend login page doesn't exist yet.
        user = (await db.execute(select(User).order_by(User.created_at).limit(1))).scalar_one_or_none()
        if user is None:
            user = User(
                email="dev@pulse.local",
                name="Dev Admin",
                role=UserRole.ADMIN,
                password_hash=hash_password("dev"),
            )
            db.add(user)
            await db.flush()
        return user

    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    user_id = _verify_token(auth.removeprefix("Bearer ").strip())
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired token")
    return await _load_user(user_id, db)
