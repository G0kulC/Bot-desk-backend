from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr

from app.models import UserRole
from app.schemas.common import ORMModel


class LoginIn(BaseModel):
    email: EmailStr
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
