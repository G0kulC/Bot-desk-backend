from __future__ import annotations

from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, User

# Never write these into the audit trail.
_REDACT = {"meta_access_token", "aisensy_api_key", "aisensy_webhook_secret", "password"}


def _clean(diff: dict[str, Any] | None) -> dict[str, Any] | None:
    if diff is None:
        return None
    out = {}
    for k, v in diff.items():
        out[k] = "***" if k in _REDACT or k.endswith("_enc") else v
    return jsonable_encoder(out)


def audit(
    session: AsyncSession,
    user: User | None,
    action: str,
    entity: str,
    entity_id: object | None = None,
    diff: dict[str, Any] | None = None,
) -> None:
    """Add an audit row to the session; the caller's commit persists it."""
    session.add(
        AuditLog(
            user_id=user.id if user else None,
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id is not None else None,
            diff=_clean(diff),
        )
    )


def changes(obj: object, data: dict[str, Any]) -> dict[str, Any]:
    """{field: {"from": old, "to": new}} for fields whose value would change."""
    out: dict[str, Any] = {}
    for key, new in data.items():
        old = getattr(obj, key, None)
        if old != new:
            out[key] = {"from": old, "to": new}
    return out
