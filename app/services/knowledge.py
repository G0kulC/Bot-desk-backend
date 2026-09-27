from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import KnowledgeBase, KnowledgeVersion
from app.models.knowledge import APPROVAL_SENSITIVE_FIELDS, KNOWLEDGE_FIELDS
from app.timeutil import utcnow


async def get_knowledge(session: AsyncSession, client_id: uuid.UUID) -> KnowledgeBase | None:
    return await session.scalar(select(KnowledgeBase).where(KnowledgeBase.client_id == client_id))


async def save_knowledge(
    session: AsyncSession,
    client_id: uuid.UUID,
    data: dict[str, str | None],
    saved_by: str | None = None,
    note: str | None = None,
) -> tuple[KnowledgeBase, list[str]]:
    """Save knowledge as a new version. Returns (kb, changed_fields).

    Every save bumps `version` and stores a snapshot. Approval is reset when services, faqs or
    rules change.
    """
    updates = {k: (v or "") for k, v in data.items() if k in KNOWLEDGE_FIELDS and v is not None}
    kb = await get_knowledge(session, client_id)
    if kb is None:
        kb = KnowledgeBase(
            client_id=client_id, version=1, approved=False, **dict.fromkeys(KNOWLEDGE_FIELDS, "")
        )
        for k, v in updates.items():
            setattr(kb, k, v)
        session.add(kb)
        await session.flush()
        changed = list(updates)
    else:
        changed = [k for k, v in updates.items() if getattr(kb, k) != v]
        for k in changed:
            setattr(kb, k, updates[k])
        kb.version += 1
        if any(f in changed for f in APPROVAL_SENSITIVE_FIELDS):
            kb.approved = False
            kb.approved_at = None
            kb.approved_by_name = None
    session.add(
        KnowledgeVersion(
            knowledge_base_id=kb.id,
            client_id=client_id,
            version=kb.version,
            content=kb.snapshot(),
            saved_by=saved_by,
            note=note,
        )
    )
    await session.flush()
    return kb, changed


def approve(kb: KnowledgeBase, approved_by_name: str) -> None:
    kb.approved = True
    kb.approved_at = utcnow()
    kb.approved_by_name = approved_by_name
