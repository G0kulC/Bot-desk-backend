"""The inbound message pipeline.

Webhook routes persist the raw event and return 200 immediately; `process_webhook_event` then runs
in a background task: it parses the payload with the right provider and handles each event.
Messages from one contact are processed in order under a per-contact asyncio lock.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
import weakref
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    Client,
    ClientChannel,
    ClientStatus,
    Contact,
    Direction,
    Lead,
    LeadStatus,
    Message,
    MsgStatus,
    MsgType,
    Sender,
    WebhookEvent,
)
from app.security import mask_phone
from app.services.ai.engine import AIReply, generate_reply
from app.services.ai.prompts import canned, guess_language
from app.services.alerts import alert_owner
from app.services.knowledge import get_knowledge
from app.services.messaging import recently_sent, send_text_logged
from app.services.providers.base import InboundEvent, InboundKind
from app.services.providers.factory import get_provider, get_provider_by_name
from app.textutil import strip_punctuation
from app.timeutil import utcnow

log = logging.getLogger(__name__)

STOP_WORDS = {"stop", "unsubscribe", "stop all", "நிறுத்து", "நிறுத்துங்கள்", "रोको", "बंद करो"}
START_WORDS = {"start", "subscribe", "unstop", "தொடங்கு", "शुरू"}
_STATUS_RANK = {"received": 0, "sent": 1, "delivered": 2, "read": 3}

# ------------------------------------------------------------------ per-contact ordering

_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def contact_lock(client_id: uuid.UUID, wa_id: str) -> asyncio.Lock:
    key = f"{client_id}:{wa_id}"
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


def _keyword(body: str | None) -> str:
    return strip_punctuation(body or "")


# ------------------------------------------------------------------ entry points


async def process_webhook_event(event_id: uuid.UUID) -> None:
    """Background task: parse a stored webhook payload and handle each event."""
    async with SessionLocal() as session:
        wh = await session.get(WebhookEvent, event_id)
        if wh is None or wh.processed_at is not None:
            return
        provider_name, payload, client_hint = wh.provider, wh.payload or {}, wh.client_id

    errors: list[str] = []
    try:
        events = get_provider_by_name(provider_name).parse_inbound(payload)
    except Exception as exc:
        log.exception("webhook_parse_failed", extra={"event_id": str(event_id)})
        events, errors = [], [f"parse: {exc}"]

    for ev in events:
        try:
            await handle_event(ev, client_hint)
        except Exception as exc:
            log.exception("inbound_event_failed", extra={"event_id": str(event_id), "kind": ev.kind})
            errors.append(f"{ev.kind}:{ev.provider_message_id}: {exc}")

    async with SessionLocal() as session:
        wh = await session.get(WebhookEvent, event_id)
        if wh is not None:
            wh.processed_at = utcnow()
            wh.error = "\n".join(errors)[:4000] or None
            await session.commit()


async def resolve_channel(
    session: AsyncSession, ev: InboundEvent, client_hint: uuid.UUID | None
) -> tuple[Client, ClientChannel] | None:
    if ev.channel_ref:
        stmt = select(ClientChannel).where(
            ClientChannel.meta_phone_number_id == ev.channel_ref, ClientChannel.is_active.is_(True)
        )
    elif client_hint:
        stmt = select(ClientChannel).where(
            ClientChannel.client_id == client_hint, ClientChannel.is_active.is_(True)
        )
    else:
        return None
    channel = await session.scalar(stmt)
    if channel is None:
        return None
    client = await session.get(Client, channel.client_id)
    if client is None or client.deleted_at is not None:
        return None
    return client, channel


async def handle_event(ev: InboundEvent, client_hint: uuid.UUID | None = None) -> None:
    async with SessionLocal() as session:
        resolved = await resolve_channel(session, ev, client_hint)
        if resolved is None:
            log.warning(
                "inbound_unroutable",
                extra={"provider": ev.provider, "channel_ref": ev.channel_ref, "kind": ev.kind},
            )
            return
        client, channel = resolved
        if ev.kind == InboundKind.status:
            await handle_status(session, ev)
            return
        if not ev.wa_id:
            return
        async with contact_lock(client.id, ev.wa_id):
            if ev.kind == InboundKind.agent_message:
                await handle_agent_message(session, client, ev)
            else:
                await handle_customer_message(session, client, channel, ev)


# ------------------------------------------------------------------ status + agent events


async def handle_status(session: AsyncSession, ev: InboundEvent) -> None:
    if not ev.provider_message_id or not ev.status:
        return
    msg = await session.scalar(select(Message).where(Message.provider_message_id == ev.provider_message_id))
    if msg is None:
        return
    new = ev.status.lower()
    if new == "failed":
        msg.status = MsgStatus.failed
        msg.error = ev.error or "Delivery failed"
        if msg.meta and msg.meta.get("kind") == "owner_alert":
            msg.meta = {**msg.meta, "undelivered": True}
    elif new in _STATUS_RANK and _STATUS_RANK[new] > _STATUS_RANK.get(msg.status.value, -1):
        msg.status = MsgStatus(new)
    await session.commit()


async def upsert_contact(
    session: AsyncSession, client: Client, wa_id: str, profile_name: str | None, inbound_at: datetime | None
) -> Contact:
    await session.execute(
        pg_insert(Contact)
        .values(id=uuid.uuid4(), client_id=client.id, wa_id=wa_id, handoff_active=False, opted_out=False)
        .on_conflict_do_nothing(constraint="uq_contacts_client_wa")
    )
    contact = await session.scalar(
        select(Contact).where(Contact.client_id == client.id, Contact.wa_id == wa_id)
    )
    assert contact is not None
    if profile_name:
        contact.profile_name = profile_name
    if inbound_at is not None:
        contact.last_inbound_at = inbound_at
    return contact


async def _message_exists(session: AsyncSession, provider_message_id: str | None) -> bool:
    if not provider_message_id:
        return False
    found = await session.scalar(select(Message.id).where(Message.provider_message_id == provider_message_id))
    return found is not None


async def handle_agent_message(session: AsyncSession, client: Client, ev: InboundEvent) -> None:
    """A human replied from the provider's inbox: log it and treat it as a takeover."""
    if await _message_exists(session, ev.provider_message_id):
        return
    contact = await upsert_contact(session, client, ev.wa_id, None, None)
    session.add(
        Message(
            client_id=client.id,
            contact_id=contact.id,
            direction=Direction.outbound,
            sender=Sender.agent,
            provider=ev.provider,
            provider_message_id=ev.provider_message_id,
            msg_type=MsgType(ev.msg_type) if ev.msg_type in MsgType._value2member_map_ else MsgType.other,
            body=ev.body,
            status=MsgStatus.sent,
            meta={"source": "provider_inbox"},
        )
    )
    if not contact.handoff_active:
        contact.handoff_active = True
        contact.handoff_since = utcnow()
        contact.handoff_reason = "Agent replied from the provider inbox"
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()


# ------------------------------------------------------------------ customer messages


async def load_history(
    session: AsyncSession, contact: Contact, exclude_id: uuid.UUID, turns: int
) -> list[dict]:
    rows = (
        await session.scalars(
            select(Message)
            .where(
                Message.contact_id == contact.id,
                Message.id != exclude_id,
                Message.sender.in_([Sender.customer, Sender.bot, Sender.agent]),
                Message.msg_type == MsgType.text,
                Message.body.is_not(None),
            )
            .order_by(Message.created_at.desc())
            .limit(turns)
        )
    ).all()
    return [
        {"role": "user" if m.sender == Sender.customer else "assistant", "content": m.body or ""}
        for m in reversed(rows)
    ]


async def _skip(session: AsyncSession, msg: Message, reason: str) -> None:
    msg.meta = {**(msg.meta or {}), "skip_reason": reason}
    await session.commit()
    log.info("bot_skipped", extra={"reason": reason, "message_id": str(msg.id)})


async def handle_customer_message(
    session: AsyncSession, client: Client, channel: ClientChannel, ev: InboundEvent
) -> Message | None:
    s = get_settings()

    # 1. Idempotency.
    if await _message_exists(session, ev.provider_message_id):
        return None

    # 2. Contact + inbound message.
    now = utcnow()
    inbound_at = min(ev.timestamp, now) if ev.timestamp else now
    contact = await upsert_contact(session, client, ev.wa_id, ev.profile_name, inbound_at)
    channel.last_inbound_at = now
    msg_type = MsgType(ev.msg_type) if ev.msg_type in MsgType._value2member_map_ else MsgType.other
    inbound = Message(
        client_id=client.id,
        contact_id=contact.id,
        direction=Direction.inbound,
        sender=Sender.customer,
        provider=ev.provider,
        provider_message_id=ev.provider_message_id,
        msg_type=msg_type,
        body=ev.body,
        status=MsgStatus.received,
    )
    session.add(inbound)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()  # duplicate delivered concurrently
        return None
    log.info(
        "inbound_message", extra={"client_id": str(client.id), "from": mask_phone(ev.wa_id), "type": msg_type}
    )

    provider = get_provider(client)
    if ev.provider_message_id:
        try:
            await provider.mark_read(channel, ev.provider_message_id)
        except Exception:
            log.info("mark_read_failed", exc_info=True)

    lang_hint = guess_language(ev.body, contact.detected_language)
    word = _keyword(ev.body) if msg_type == MsgType.text else ""

    # STOP / START (opt-out handling comes before the other checks).
    if word in STOP_WORDS:
        if contact.opted_out:
            await _skip(session, inbound, "opted_out")
            return inbound
        contact.opted_out = True
        await send_text_logged(
            session,
            client,
            channel,
            contact,
            canned("opt_out", lang_hint),
            Sender.bot,
            meta={"kind": "opt_out"},
        )
        await _skip(session, inbound, "opt_out_requested")
        return inbound
    if word in START_WORDS and contact.opted_out:
        contact.opted_out = False
        if client.bot_enabled and client.status != ClientStatus.paused:
            await send_text_logged(
                session,
                client,
                channel,
                contact,
                canned("opt_in", lang_hint),
                Sender.bot,
                meta={"kind": "opt_in"},
            )
        await _skip(session, inbound, "opt_in_requested")
        return inbound

    # 3. Reasons to stay silent.
    if not client.bot_enabled:
        await _skip(session, inbound, "bot_disabled")
        return inbound
    if client.status == ClientStatus.paused:
        await _skip(session, inbound, "client_paused")
        return inbound
    if contact.opted_out:
        await _skip(session, inbound, "opted_out")
        return inbound
    if contact.handoff_active:
        await _skip(session, inbound, "handoff_active")
        return inbound

    # Non-text (image, audio, location...): store it and say a person will check it.
    if msg_type != MsgType.text or not (ev.body or "").strip():
        if not await recently_sent(session, contact, "non_text_ack", 10):
            await send_text_logged(
                session, client, channel, contact, canned("non_text", lang_hint), Sender.bot,
                meta={"kind": "non_text_ack"},
            )  # fmt: skip
        await _skip(session, inbound, f"non_text:{msg_type.value}")
        return inbound

    # 4. Knowledge.
    kb = await get_knowledge(session, client.id)
    if kb is None or (not kb.approved and client.status == ClientStatus.live):
        reason = "knowledge_missing" if kb is None else "knowledge_not_approved"
        if not await recently_sent(session, contact, "holding", 30):
            await send_text_logged(
                session,
                client,
                channel,
                contact,
                canned("holding", lang_hint),
                Sender.bot,
                meta={"kind": "holding"},
            )
            await alert_owner(
                session, client, channel, contact, "kb_not_approved",
                f"Message: {(ev.body or '')[:200]}\nReason: {reason.replace('_', ' ')}",
            )  # fmt: skip
        await _skip(session, inbound, reason)
        return inbound

    # 5-7. AI reply (with fallback model) + guardrails.
    history = await load_history(session, contact, inbound.id, s.AI_HISTORY_TURNS)
    allowed_extra = "\n".join(
        [f"+{contact.wa_id}", ev.body or ""] + [h["content"] for h in history if h["role"] == "user"]
    )
    result = await generate_reply(client, kb, history, ev.body or "", extra_allowed_text=allowed_extra)

    if not result.ok or result.reply is None:
        await send_text_logged(
            session, client, channel, contact, canned("fallback", lang_hint), Sender.bot,
            meta={"kind": "ai_fallback", "errors": result.errors},
        )  # fmt: skip
        await alert_owner(session, client, channel, contact, "ai_failed", f"Message: {(ev.body or '')[:200]}")
        inbound.meta = {**(inbound.meta or {}), "ai_errors": result.errors}
        await session.commit()
        return inbound

    reply: AIReply = result.reply
    contact.detected_language = reply.language[:32]

    # 9. Send (the customer just wrote, so we are inside the 24-hour window).
    await send_text_logged(
        session,
        client,
        channel,
        contact,
        reply.reply,
        Sender.bot,
        meta={
            "kind": "ai_reply",
            "language": reply.language,
            "guardrail_notes": result.guardrail_notes,
            "used_fallback": result.used_fallback,
            "reply_to": str(inbound.id),
        },
        ai_model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_usd=result.cost_usd,
        latency_ms=result.latency_ms,
    )

    # 10. Lead.
    if reply.lead is not None:
        lead, changed = await upsert_lead(session, client, contact, inbound, reply)
        if changed:
            detail = f"Need: {lead.need or '-'}\nName: {lead.name or '-'}\nWhen: {lead.preferred_time or '-'}"
            await alert_owner(session, client, channel, contact, "lead", detail)

    # 11. Handoff.
    if reply.handoff:
        contact.handoff_active = True
        contact.handoff_since = utcnow()
        contact.handoff_reason = (reply.handoff_reason or "Assistant requested a person")[:500]
        await alert_owner(
            session, client, channel, contact, "handoff",
            f"Reason: {contact.handoff_reason}\nLast message: {(ev.body or '')[:200]}",
        )  # fmt: skip

    await session.commit()
    return inbound


async def upsert_lead(
    session: AsyncSession, client: Client, contact: Contact, source: Message, reply: AIReply
) -> tuple[Lead, bool]:
    """One open lead per contact: create it, or fill in new details. Returns (lead, changed)."""
    info = reply.lead
    assert info is not None
    lead = await session.scalar(
        select(Lead)
        .where(Lead.contact_id == contact.id, Lead.status.in_([LeadStatus.new, LeadStatus.contacted]))
        .order_by(Lead.created_at.desc())
        .limit(1)
    )
    phone = info.phone or f"+{contact.wa_id}"
    name = info.name or contact.profile_name or ""
    if lead is None:
        lead = Lead(
            client_id=client.id,
            contact_id=contact.id,
            name=name[:255],
            phone=phone[:32],
            need=info.need,
            preferred_time=info.when[:255],
            status=LeadStatus.new,
            source_message_id=source.id,
        )
        session.add(lead)
        await session.flush()
        return lead, True
    changed = False
    for attr, value in (
        ("name", info.name),
        ("phone", info.phone),
        ("need", info.need),
        ("preferred_time", info.when),
    ):
        if value and getattr(lead, attr) != value:
            setattr(lead, attr, value)
            changed = True
    return lead, changed


__all__ = [
    "contact_lock",
    "handle_customer_message",
    "handle_event",
    "process_webhook_event",
    "upsert_contact",
]
