from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.models import UserRole
from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    # Plain string: login only looks the user up, so don't reject special-use domains like .local
    email: str = Field(min_length=3, max_length=320)
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole
    is_active: bool
