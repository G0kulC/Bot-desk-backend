from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.errors import AppError
from app.models import User
from app.schemas.auth import LoginIn, TokenOut, UserOut
from app.security import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: SessionDep) -> TokenOut:
    user = await session.scalar(select(User).where(func.lower(User.email) == body.email.lower()))
    if user is None or not user.is_active or not verify_password(body.password, user.password_hash):
        raise AppError(401, "invalid_credentials", "Email or password is incorrect")
    return TokenOut(access_token=create_access_token(str(user.id), {"role": user.role.value}))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
