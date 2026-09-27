"""Scheduled job bodies. Each takes a session so tests can call them directly."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    AttentionItem,
    Client,
    ClientChannel,
    ClientStatus,
    Contact,
    Message,
    Sender,
    WebhookEvent,
)
from app.services.billing import BillingStatus, billing_for_clients
from app.timeutil import today_ist, utcnow

log = logging.getLogger(__name__)

AUTO_KINDS = ("trial_ending", "payment_due", "payment_overdue", "channel_silent")


async def release_stale_handoffs(session: AsyncSession, now: datetime | None = None) -> int:
    """Turn off handoff when the latest agent/customer message is older than HANDOFF_AUTO_RELEASE_HOURS."""
    now = now or utcnow()
    cutoff = now - timedelta(hours=get_settings().HANDOFF_AUTO_RELEASE_HOURS)
    last_human = (
        select(func.max(Message.created_at))
        .where(Message.contact_id == Contact.id, Message.sender.in_([Sender.agent, Sender.customer]))
        .correlate(Contact)
        .scalar_subquery()
    )
    ref = func.coalesce(last_human, Contact.handoff_since, Contact.created_at)
    result = await session.execute(
        update(Contact)
        .where(Contact.handoff_active.is_(True), ref < cutoff)
        .values(handoff_active=False, handoff_since=None, handoff_reason=None)
        .execution_options(synchronize_session=False)
    )
    await session.commit()
    count = result.rowcount or 0
    if count:
        log.info("handoffs_released", extra={"count": count})
    return count


async def _upsert_attention(session: AsyncSession, client_id, kind: str, text: str, key: str) -> None:
    stmt = pg_insert(AttentionItem).values(client_id=client_id, kind=kind, text=text, dedupe_key=key)
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["dedupe_key"],
            set_={"resolved_at": None, "text": stmt.excluded.text, "updated_at": func.now()},
        )
    )


async def build_attention_items(session: AsyncSession, today: date | None = None) -> int:
    """Daily: trials ending in <= 2 days, payments due/overdue, channels silent for 3 days.

    Auto items are re-evaluated every run: ones whose condition cleared are resolved.
    """
    s = get_settings()
    today = today or today_ist()
    now = utcnow()
    await session.execute(
        update(AttentionItem)
        .where(AttentionItem.kind.in_(AUTO_KINDS), AttentionItem.resolved_at.is_(None))
        .values(resolved_at=now)
    )
    clients = list((await session.scalars(select(Client).where(Client.deleted_at.is_(None)))).all())
    created = 0

    for c in clients:
        if c.status == ClientStatus.trial and c.trial_start:
            end = c.trial_start + timedelta(days=s.TRIAL_DAYS)
            days_left = (end - today).days
            if 0 <= days_left <= 2:
                when = "today" if days_left == 0 else f"in {days_left} day{'s' if days_left > 1 else ''}"
                text = f"{c.name}: trial ends {when} ({end:%d %b}). Send the report."
                await _upsert_attention(
                    session, c.id, "trial_ending", text, f"trial_ending:{c.id}:{end.isoformat()}"
                )
                created += 1

    live = [c for c in clients if c.status == ClientStatus.live]
    for c in live:
        info = (await billing_for_clients(session, [c], today))[c.id]
        if info.status in (BillingStatus.due, BillingStatus.overdue) and info.due_date:
            kind = "payment_overdue" if info.status == BillingStatus.overdue else "payment_due"
            await _upsert_attention(
                session, c.id, kind,
                f"{c.name}: ₹{c.monthly_fee:,.0f} {info.status} (due {info.due_date:%d %b})",
                f"{kind}:{c.id}:{info.due_date.isoformat()}",
            )  # fmt: skip
            created += 1

    silent_cutoff = now - timedelta(days=3)
    active_ids = {c.id: c for c in clients if c.status in (ClientStatus.live, ClientStatus.trial)}
    if active_ids:
        channels = (
            await session.scalars(
                select(ClientChannel).where(
                    ClientChannel.is_active.is_(True),
                    ClientChannel.client_id.in_(list(active_ids)),
                    func.coalesce(ClientChannel.last_inbound_at, ClientChannel.created_at) < silent_cutoff,
                )
            )
        ).all()
        for ch in channels:
            c = active_ids[ch.client_id]
            last = ch.last_inbound_at
            since = f"since {last.date():%d %b}" if last else "ever"
            await _upsert_attention(
                session, c.id, "channel_silent",
                f"{c.name}: no customer messages {since}. Check the WhatsApp connection.",
                f"channel_silent:{c.id}:{last.date().isoformat() if last else 'never'}",
            )  # fmt: skip
            created += 1

    await session.commit()
    log.info("attention_items_built", extra={"count": created})
    return created


async def purge_old_webhook_payloads(session: AsyncSession, days: int = 30) -> int:
    """Nightly: drop raw payloads older than N days; keep the rows (idempotency + audit)."""
    result = await session.execute(
        update(WebhookEvent)
        .where(WebhookEvent.received_at < utcnow() - timedelta(days=days), WebhookEvent.payload.is_not(None))
        .values(payload=None)
    )
    await session.commit()
    return result.rowcount or 0


async def _run(fn, name: str) -> None:
    try:
        async with SessionLocal() as session:
            await fn(session)
    except Exception:
        log.exception("job_failed", extra={"job": name})


async def job_release_handoffs() -> None:
    await _run(release_stale_handoffs, "release_handoffs")


async def job_attention() -> None:
    await _run(build_attention_items, "attention")


async def job_purge_payloads() -> None:
    await _run(purge_old_webhook_payloads, "purge_payloads")
