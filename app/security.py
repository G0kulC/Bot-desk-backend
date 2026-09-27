from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.config import get_settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _pwd.verify(password, password_hash)
    except ValueError:
        return False


def create_access_token(subject: str, extra: dict | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES)).timestamp()),
        **(extra or {}),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, get_settings().JWT_SECRET, algorithms=[JWT_ALGORITHM])


def _fernet() -> Fernet:
    key = get_settings().FERNET_KEY
    if not key:
        raise RuntimeError("FERNET_KEY is not set")
    return Fernet(key.encode())


def encrypt_secret(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Could not decrypt a stored secret (was FERNET_KEY changed?)") from exc


def secret_hint(value_enc: str | None) -> dict:
    """Masked view of an encrypted secret: never returns the secret itself."""
    if not value_enc:
        return {"has_token": False, "last4": None}
    plain = decrypt_secret(value_enc) or ""
    return {"has_token": True, "last4": plain[-4:] if len(plain) >= 4 else None}


def new_channel_token() -> str:
    return secrets.token_urlsafe(24)


def mask_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"***{digits[-4:]}" if digits else "***"
