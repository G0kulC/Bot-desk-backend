from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select, true

from app.api.deps import CurrentUser, SessionDep
from app.errors import AppError, not_found
from app.models import Client, Contact, Direction, Message, Sender
from app.schemas.inbox import ContactOut, HandoffIn, InboxItem, MessageOut, OptOutIn, ReplyIn
from app.services.audit import audit
from app.services.clients import get_active_channel
from app.services.messaging import send_text_logged
from app.timeutil import utcnow

router = APIRouter(tags=["inbox"])

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def in_24h_window(contact: Contact) -> bool:
    return contact.last_inbound_at is not None and contact.last_inbound_at >= utcnow() - timedelta(hours=24)


async def _contact_or_404(session: SessionDep, contact_id: uuid.UUID) -> tuple[Contact, Client]:
    contact = await session.get(Contact, contact_id)
    if contact is None:
        raise not_found("Contact")
    client = await session.get(Client, contact.client_id)
    if client is None or client.deleted_at is not None:
        raise not_found("Contact")
    return contact, client


@router.get("/inbox", response_model=list[InboxItem])
async def inbox(
    session: SessionDep,
    _: CurrentUser,
    client_id: uuid.UUID | None = None,
    handoff: bool | None = None,
    q: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> list[InboxItem]:
    """Contacts sorted by last message, with unread count and a preview of the last message."""
    last = (
        select(Message.body, Message.created_at, Message.sender)
        .where(Message.contact_id == Contact.id)
        .order_by(Message.created_at.desc())
        .limit(1)
        .lateral("last_msg")
    )
    unread = (
        select(func.count(Message.id))
        .where(
            Message.contact_id == Contact.id,
            Message.direction == Direction.inbound,
            Message.created_at > func.coalesce(Contact.last_read_at, _EPOCH),
        )
        .correlate(Contact)
        .scalar_subquery()
    )
    stmt = (
        select(Contact, Client.name, last.c.body, last.c.created_at, last.c.sender, unread)
        .join(Client, Client.id == Contact.client_id)
        .join(last, true())
        .where(Client.deleted_at.is_(None))
    )
    if client_id:
        stmt = stmt.where(Contact.client_id == client_id)
    if handoff is not None:
        stmt = stmt.where(Contact.handoff_active.is_(handoff))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Contact.profile_name.ilike(like), Contact.wa_id.ilike(like)))
    rows = (await session.execute(stmt.order_by(last.c.created_at.desc()).offset(offset).limit(limit))).all()
    return [
        InboxItem(
            contact_id=c.id,
            client_id=c.client_id,
            client_name=client_name,
            wa_id=c.wa_id,
            profile_name=c.profile_name,
            detected_language=c.detected_language,
            handoff_active=c.handoff_active,
            handoff_reason=c.handoff_reason,
            opted_out=c.opted_out,
            last_inbound_at=c.last_inbound_at,
            can_reply=in_24h_window(c),
            unread_count=unread_count or 0,
            last_message_at=last_at,
            last_message_preview=(body or "")[:120] or None,
            last_message_sender=sender,
        )
        for c, client_name, body, last_at, sender, unread_count in rows
    ]


@router.get("/contacts/{contact_id}", response_model=ContactOut)
async def get_contact(contact_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> Contact:
    contact, _client = await _contact_or_404(session, contact_id)
    return contact


@router.get("/contacts/{contact_id}/messages", response_model=list[MessageOut])
async def contact_messages(
    contact_id: uuid.UUID,
    session: SessionDep,
    _: CurrentUser,
    before: datetime | None = Query(None, description="Return messages older than this timestamp"),
    limit: int = Query(50, ge=1, le=200),
) -> list[Message]:
    """Oldest-to-newest page of messages. Without `before`, returns the latest page and marks it read."""
    contact, _client = await _contact_or_404(session, contact_id)
    stmt = select(Message).where(Message.contact_id == contact_id)
    if before is not None:
        stmt = stmt.where(Message.created_at < before)
    rows = list((await session.scalars(stmt.order_by(Message.created_at.desc()).limit(limit))).all())
    if before is None:
        contact.last_read_at = utcnow()
        await session.commit()
    return list(reversed(rows))


@router.post("/contacts/{contact_id}/reply", response_model=MessageOut)
async def reply(contact_id: uuid.UUID, body: ReplyIn, session: SessionDep, user: CurrentUser) -> Message:
    """Send a message as a human agent. Only allowed inside WhatsApp's 24-hour customer-care window."""
    contact, client = await _contact_or_404(session, contact_id)
    if not in_24h_window(contact):
        raise AppError(
            409,
            "outside_24h_window",
            "The customer last wrote more than 24 hours ago. WhatsApp only allows approved templates now.",
        )
    channel = await get_active_channel(session, client.id)
    msg = await send_text_logged(
        session, client, channel, contact, body.body.strip(), Sender.agent, meta={"by": user.email}
    )
    # A person is now talking: keep the bot quiet until released.
    if not contact.handoff_active:
        contact.handoff_active = True
        contact.handoff_since = utcnow()
        contact.handoff_reason = f"Agent reply by {user.full_name or user.email}"
    contact.last_read_at = utcnow()
    await session.commit()
    await session.refresh(msg)
    if msg.status.value == "failed":
        raise AppError(502, "provider_error", f"WhatsApp send failed: {msg.error}")
    return msg


@router.post("/contacts/{contact_id}/handoff", response_model=ContactOut)
async def set_handoff(
    contact_id: uuid.UUID, body: HandoffIn, session: SessionDep, user: CurrentUser
) -> Contact:
    contact, _client = await _contact_or_404(session, contact_id)
    contact.handoff_active = body.active
    contact.handoff_since = utcnow() if body.active else None
    contact.handoff_reason = (body.reason or f"Set by {user.email}") if body.active else None
    audit(session, user, "contact.handoff", "contact", contact.id, {"active": body.active})
    await session.commit()
    await session.refresh(contact)
    return contact


@router.post("/contacts/{contact_id}/opt-out", response_model=ContactOut)
async def set_opt_out(
    contact_id: uuid.UUID, body: OptOutIn, session: SessionDep, user: CurrentUser
) -> Contact:
    contact, _client = await _contact_or_404(session, contact_id)
    contact.opted_out = body.opted_out
    audit(session, user, "contact.opt_out", "contact", contact.id, {"opted_out": body.opted_out})
    await session.commit()
    await session.refresh(contact)
    return contact
