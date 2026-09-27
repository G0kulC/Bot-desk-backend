from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.errors import AppError, not_found
from app.models import Client, Contact, Lead, LeadStatus
from app.schemas.inbox import LeadCreate, LeadOut, LeadUpdate
from app.services.audit import audit, changes
from app.services.clients import get_client_or_404

router = APIRouter(prefix="/leads", tags=["leads"])


@router.get("", response_model=list[LeadOut])
async def list_leads(
    session: SessionDep,
    _: CurrentUser,
    client_id: uuid.UUID | None = None,
    contact_id: uuid.UUID | None = None,
    status_: LeadStatus | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[Lead]:
    stmt = select(Lead).join(Client, Client.id == Lead.client_id).where(Client.deleted_at.is_(None))
    if client_id:
        stmt = stmt.where(Lead.client_id == client_id)
    if contact_id:
        stmt = stmt.where(Lead.contact_id == contact_id)
    if status_:
        stmt = stmt.where(Lead.status == status_)
    rows = await session.scalars(stmt.order_by(Lead.created_at.desc()).offset(offset).limit(limit))
    return list(rows)


@router.post("", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
async def create_lead(body: LeadCreate, session: SessionDep, user: CurrentUser) -> Lead:
    await get_client_or_404(session, body.client_id)
    if body.contact_id:
        contact = await session.get(Contact, body.contact_id)
        if contact is None or contact.client_id != body.client_id:
            raise AppError(422, "validation_error", "contact_id does not belong to this client")
    lead = Lead(**body.model_dump())
    session.add(lead)
    await session.flush()
    audit(session, user, "lead.create", "lead", lead.id, body.model_dump())
    await session.commit()
    await session.refresh(lead)
    return lead


@router.patch("/{lead_id}", response_model=LeadOut)
async def update_lead(lead_id: uuid.UUID, body: LeadUpdate, session: SessionDep, user: CurrentUser) -> Lead:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        raise not_found("Lead")
    data = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None or k == "notes"}
    diff = changes(lead, data)
    for k, v in data.items():
        setattr(lead, k, v)
    if diff:
        audit(session, user, "lead.update", "lead", lead.id, diff)
    await session.commit()
    await session.refresh(lead)
    return lead
