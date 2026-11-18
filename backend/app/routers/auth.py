from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import create_token, get_current_user, hash_password
from app.models import User
from app.resilience import get_db
from app.schemas import LoginRequest
from app.serializers import user_public

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email))).scalar_one_or_none()
    if user is None or user.password_hash != hash_password(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return {"token": create_token(user), "user": user_public(user)}


@router.post("/logout")
async def logout():
    # Stateless tokens: the client discards it. Token revocation would need a blocklist.
    return {"status": "logged out"}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return user_public(user)
