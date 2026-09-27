"""Send a WhatsApp message through the client's provider and log it in `messages`."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, ClientChannel, Contact, Direction, Message, MsgStatus, MsgType, Sender
from app.security import mask_phone
from app.services.providers.base import SendResult
from app.services.providers.factory import effective_provider, get_provider
from app.timeutil import utcnow

log = logging.getLogger(__name__)


async def send_text_logged(
    session: AsyncSession,
    client: Client,
    channel: ClientChannel | None,
    contact: Contact,
    body: str,
    sender: Sender,
    *,
    meta: dict[str, Any] | None = None,
    ai_model: str | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_usd: Decimal | None = None,
    latency_ms: int | None = None,
) -> Message:
    if channel is None:
        result = SendResult(ok=False, error="No active WhatsApp channel for this client")
    else:
        result = await get_provider(client).send_text(channel, contact.wa_id, body)
    return record_outbound(
        session,
        client,
        channel,
        contact,
        body,
        sender,
        result,
        msg_type=MsgType.text,
        meta=meta,
        ai_model=ai_model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
    )


def record_outbound(
    session: AsyncSession,
    client: Client,
    channel: ClientChannel | None,
    contact: Contact,
    body: str,
    sender: Sender,
    result: SendResult,
    *,
    msg_type: MsgType = MsgType.text,
    meta: dict[str, Any] | None = None,
    **ai: Any,
) -> Message:
    if not result.ok:
        log.warning(
            "whatsapp_send_failed",
            extra={"client_id": str(client.id), "to": mask_phone(contact.wa_id), "error": result.error},
        )
        if channel is not None:
            channel.last_error = f"{utcnow().isoformat()} {result.error}"
    msg = Message(
        client_id=client.id,
        contact_id=contact.id,
        direction=Direction.outbound,
        sender=sender,
        provider=effective_provider(client),
        provider_message_id=result.provider_message_id,
        msg_type=msg_type,
        body=body,
        status=MsgStatus.sent if result.ok else MsgStatus.failed,
        error=result.error,
        meta=meta,
        **{k: v for k, v in ai.items() if v is not None},
    )
    session.add(msg)
    return msg


async def recently_sent(session: AsyncSession, contact: Contact, kind: str, minutes: int) -> bool:
    """True if a message with meta.kind == kind went to this contact in the last N minutes."""
    since = utcnow() - timedelta(minutes=minutes)
    found = await session.scalar(
        select(Message.id)
        .where(
            Message.contact_id == contact.id,
            Message.direction == Direction.outbound,
            Message.created_at >= since,
            Message.meta["kind"].astext == kind,
        )
        .limit(1)
    )
    return found is not None
