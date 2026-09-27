from __future__ import annotations

import uuid
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.errors import AppError
from app.models import User
from app.security import decode_access_token

_bearer = HTTPBearer(auto_error=False, description="Admin JWT from POST /api/v1/auth/login")

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> User:
    if creds is None:
        raise AppError(401, "unauthorized", "Missing bearer token")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise AppError(401, "unauthorized", "Invalid or expired token") from exc
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise AppError(401, "unauthorized", "User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
