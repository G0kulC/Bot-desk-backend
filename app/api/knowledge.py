from __future__ import annotations

import uuid

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.errors import AppError, not_found
from app.models import KnowledgeBase, KnowledgeVersion, Niche
from app.schemas.knowledge import (
    ApproveIn,
    KnowledgeIn,
    KnowledgeOut,
    KnowledgeTemplateOut,
    KnowledgeVersionOut,
)
from app.seed_data import template_for
from app.services import knowledge as kb_service
from app.services.ai.prompts import build_system_prompt
from app.services.audit import audit
from app.services.clients import get_client_or_404

router = APIRouter(tags=["knowledge"])


async def _kb_or_404(session: SessionDep, client_id: uuid.UUID) -> KnowledgeBase:
    kb = await kb_service.get_knowledge(session, client_id)
    if kb is None:
        raise not_found("Knowledge base")
    return kb


@router.get("/clients/{client_id}/knowledge", response_model=KnowledgeOut)
async def get_knowledge(client_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> KnowledgeBase:
    await get_client_or_404(session, client_id)
    return await _kb_or_404(session, client_id)


@router.put("/clients/{client_id}/knowledge", response_model=KnowledgeOut)
async def put_knowledge(
    client_id: uuid.UUID, body: KnowledgeIn, session: SessionDep, user: CurrentUser
) -> KnowledgeBase:
    await get_client_or_404(session, client_id)
    data = body.model_dump(exclude={"note"})
    kb, changed = await kb_service.save_knowledge(
        session, client_id, data, saved_by=user.full_name or user.email, note=body.note
    )
    audit(
        session, user, "knowledge.save", "knowledge_base", kb.id, {"version": kb.version, "changed": changed}
    )
    await session.commit()
    await session.refresh(kb)
    return kb


@router.post("/clients/{client_id}/knowledge/approve", response_model=KnowledgeOut)
async def approve_knowledge(
    client_id: uuid.UUID, body: ApproveIn, session: SessionDep, user: CurrentUser
) -> KnowledgeBase:
    await get_client_or_404(session, client_id)
    kb = await _kb_or_404(session, client_id)
    if not kb.services.strip():
        raise AppError(409, "knowledge_incomplete", "Add services and prices before approving")
    kb_service.approve(kb, body.approved_by_name)
    audit(
        session,
        user,
        "knowledge.approve",
        "knowledge_base",
        kb.id,
        {"version": kb.version, **body.model_dump()},
    )
    await session.commit()
    await session.refresh(kb)
    return kb


@router.get("/clients/{client_id}/knowledge/versions", response_model=list[KnowledgeVersionOut])
async def list_versions(client_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> list[KnowledgeVersion]:
    await get_client_or_404(session, client_id)
    rows = await session.scalars(
        select(KnowledgeVersion)
        .where(KnowledgeVersion.client_id == client_id)
        .order_by(KnowledgeVersion.version.desc())
    )
    return list(rows)


@router.post("/clients/{client_id}/knowledge/restore/{version}", response_model=KnowledgeOut)
async def restore_version(
    client_id: uuid.UUID, version: int, session: SessionDep, user: CurrentUser
) -> KnowledgeBase:
    await get_client_or_404(session, client_id)
    snap = await session.scalar(
        select(KnowledgeVersion).where(
            KnowledgeVersion.client_id == client_id, KnowledgeVersion.version == version
        )
    )
    if snap is None:
        raise not_found(f"Knowledge version {version}")
    kb, changed = await kb_service.save_knowledge(
        session,
        client_id,
        dict(snap.content),
        saved_by=user.full_name or user.email,
        note=f"Restored from version {version}",
    )
    audit(
        session,
        user,
        "knowledge.restore",
        "knowledge_base",
        kb.id,
        {"from_version": version, "new_version": kb.version, "changed": changed},
    )
    await session.commit()
    await session.refresh(kb)
    return kb


@router.get(
    "/clients/{client_id}/knowledge/export",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/plain": {}}, "description": "System prompt as plain text"}},
)
async def export_knowledge(client_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> PlainTextResponse:
    """The full system prompt as plain text, for pasting into other platforms."""
    client = await get_client_or_404(session, client_id)
    kb = await _kb_or_404(session, client_id)
    return PlainTextResponse(
        build_system_prompt(client, kb),
        headers={"X-Knowledge-Version": str(kb.version), "X-Knowledge-Approved": str(kb.approved).lower()},
    )


@router.get("/knowledge/templates/{niche}", response_model=KnowledgeTemplateOut)
async def get_template(niche: Niche, _: CurrentUser) -> KnowledgeTemplateOut:
    return KnowledgeTemplateOut(**template_for(niche.value))
