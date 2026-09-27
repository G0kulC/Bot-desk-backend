"""Monthly report numbers (per client) and the admin dashboard summary."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    AttentionItem,
    Client,
    ClientStatus,
    Contact,
    Direction,
    Lead,
    Message,
    MsgStatus,
    Payment,
    Sender,
)
from app.services.billing import BillingStatus, billing_for_clients
from app.textutil import strip_punctuation
from app.timeutil import is_night_ist, ist_month_bounds_utc, today_ist, utcnow


def normalise_question(text: str) -> str:
    return strip_punctuation(text, keep="₹")


def _inr(usd: Decimal | float | None) -> Decimal:
    rate = Decimal(str(get_settings().USD_TO_INR))
    return (Decimal(str(usd or 0)) * rate).quantize(Decimal("0.01"))


async def monthly_report(session: AsyncSession, client_id: uuid.UUID, year: int, month: int) -> dict:
    s = get_settings()
    start, end = ist_month_bounds_utc(year, month)
    rows = (
        await session.execute(
            select(
                Message.contact_id,
                Message.direction,
                Message.sender,
                Message.body,
                Message.msg_type,
                Message.created_at,
                Message.cost_usd,
                Message.meta,
            )
            .where(Message.client_id == client_id, Message.created_at >= start, Message.created_at < end)
            .order_by(Message.contact_id, Message.created_at)
        )
    ).all()

    inbound = [r for r in rows if r.direction == Direction.inbound]
    bot = [r for r in rows if r.sender == Sender.bot]
    agent = [r for r in rows if r.sender == Sender.agent]
    handoff_alerts = [
        r for r in rows if r.sender == Sender.system and (r.meta or {}).get("alert_kind") == "handoff"
    ]
    chat_contacts = {r.contact_id for r in inbound}
    night = sum(1 for r in inbound if is_night_ist(r.created_at, s.NIGHT_START_HOUR, s.NIGHT_END_HOUR))

    questions = Counter(
        q
        for r in inbound
        if r.msg_type.value == "text" and (q := normalise_question(r.body or "")) and len(q) > 1
    )

    # Reply time: bot reply minus the latest customer message before it (same contact).
    gaps: list[float] = []
    last_customer: dict[uuid.UUID, object] = {}
    for r in rows:
        if r.sender == Sender.customer:
            last_customer[r.contact_id] = r.created_at
        elif r.sender == Sender.bot and r.contact_id in last_customer:
            gaps.append((r.created_at - last_customer.pop(r.contact_id)).total_seconds())

    languages: dict[str, int] = {}
    if chat_contacts:
        lang_rows = (
            await session.execute(
                select(Contact.detected_language, func.count())
                .where(Contact.id.in_(chat_contacts))
                .group_by(Contact.detected_language)
            )
        ).all()
        languages = {(lang or "Unknown"): n for lang, n in lang_rows}

    leads = await session.scalar(
        select(func.count(Lead.id)).where(
            Lead.client_id == client_id, Lead.created_at >= start, Lead.created_at < end
        )
    )
    cost_usd = sum((r.cost_usd or Decimal("0")) for r in rows)
    messages_in = len(inbound)
    return {
        "client_id": client_id,
        "month": f"{year:04d}-{month:02d}",
        "chats": len(chat_contacts),
        "messages_in": messages_in,
        "messages_out": len(bot) + len(agent),
        "bot_replies": len(bot),
        "agent_replies": len(agent),
        "leads": leads or 0,
        "handoffs": len(handoff_alerts),
        "night_enquiries": night,
        "night_share": round(night / messages_in, 3) if messages_in else 0.0,
        "top_questions": [{"question": q, "count": n} for q, n in questions.most_common(10)],
        "languages": languages,
        "avg_bot_reply_seconds": round(sum(gaps) / len(gaps), 1) if gaps else None,
        "ai_cost_inr": _inr(cost_usd),
    }


@dataclass
class Attention:
    client_id: uuid.UUID | None
    kind: str
    text: str
    id: uuid.UUID | None = None


async def dashboard_summary(session: AsyncSession) -> dict:
    s = get_settings()
    today = today_ist()
    now = utcnow()
    clients = list((await session.scalars(select(Client).where(Client.deleted_at.is_(None)))).all())
    live = [c for c in clients if c.status == ClientStatus.live]
    billing = await billing_for_clients(session, live, today)
    overdue = [c for c in live if billing[c.id].status == BillingStatus.overdue]

    month_start = today.replace(day=1)
    collected = await session.scalar(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            Payment.paid_on >= month_start, Payment.paid_on <= today
        )
    )
    trials_ending = [
        c
        for c in clients
        if c.status == ClientStatus.trial
        and c.trial_start is not None
        and today <= c.trial_start + timedelta(days=s.TRIAL_DAYS) <= today + timedelta(days=7)
    ]
    active_ids = [c.id for c in clients]
    leads_7d = await session.scalar(
        select(func.count(Lead.id)).where(
            Lead.created_at >= now - timedelta(days=7), Lead.client_id.in_(active_ids)
        )
    )
    handoffs_open = await session.scalar(
        select(func.count(Contact.id)).where(
            Contact.handoff_active.is_(True), Contact.client_id.in_(active_ids)
        )
    )
    messages_7d = await session.scalar(
        select(func.count(Message.id)).where(
            Message.created_at >= now - timedelta(days=7),
            Message.sender != Sender.system,
            Message.client_id.in_(active_ids),
        )
    )
    cost_30d = await session.scalar(
        select(func.coalesce(func.sum(Message.cost_usd), 0)).where(
            Message.created_at >= now - timedelta(days=30)
        )
    )

    names = {c.id: c.name for c in clients}
    attention: list[Attention] = []
    items = (
        await session.scalars(
            select(AttentionItem)
            .where(AttentionItem.resolved_at.is_(None))
            .order_by(AttentionItem.created_at.desc())
            .limit(100)
        )
    ).all()
    attention += [
        Attention(i.client_id, i.kind, i.text, i.id) for i in items if i.client_id in names or not i.client_id
    ]
    have = {(a.client_id, a.kind) for a in attention}

    # Live items (always current, not waiting for the 09:00 job).
    for c in live:
        info = billing[c.id]
        if info.status in (BillingStatus.due, BillingStatus.overdue) and info.due_date:
            kind = f"payment_{info.status}"
            if (c.id, kind) not in have:
                attention.append(
                    Attention(
                        c.id,
                        kind,
                        f"{c.name}: ₹{c.monthly_fee:,.0f} {info.status} (due {info.due_date:%d %b})",
                    )
                )
        if not info.setup_paid and c.setup_fee > 0:
            attention.append(
                Attention(c.id, "setup_unpaid", f"{c.name}: setup fee ₹{c.setup_fee:,.0f} not recorded")
            )
    waiting = (
        await session.execute(
            select(Contact.client_id, func.count(Contact.id))
            .where(Contact.handoff_active.is_(True), Contact.client_id.in_(active_ids))
            .group_by(Contact.client_id)
        )
    ).all()
    for client_id, n in waiting:
        chats = "chat is" if n == 1 else "chats are"
        attention.append(
            Attention(client_id, "handoff_waiting", f"{names[client_id]}: {n} {chats} waiting for a person")
        )

    undelivered = (
        await session.execute(
            select(Message.client_id, Message.meta, Message.error, Message.created_at)
            .where(
                Message.sender == Sender.system,
                Message.status == MsgStatus.failed,
                Message.created_at >= now - timedelta(days=7),
                Message.client_id.in_(active_ids),
            )
            .order_by(Message.created_at.desc())
            .limit(50)
        )
    ).all()
    for client_id, meta, error, _created in undelivered:
        kind = (meta or {}).get("alert_kind", "alert")
        attention.append(
            Attention(
                client_id,
                "alert_undelivered",
                f"{names.get(client_id, 'Client')}: alert ({kind}) not delivered – {error or 'unknown'}",
            )
        )

    return {
        "paying_clients": len(live),
        "goal": 10,
        "mrr": sum((c.monthly_fee for c in live), Decimal("0.00")),
        "collected_this_month": Decimal(collected or 0).quantize(Decimal("0.01")),
        "overdue_amount": sum((c.monthly_fee for c in overdue), Decimal("0.00")),
        "overdue_count": len(overdue),
        "trials_ending_7d": len(trials_ending),
        "leads_new_7d": leads_7d or 0,
        "handoffs_open": handoffs_open or 0,
        "messages_7d": messages_7d or 0,
        "ai_cost_inr_30d": _inr(cost_30d),
        "pipeline": {st.value: sum(1 for c in clients if c.status == st) for st in ClientStatus},
        "attention": [a.__dict__ for a in attention],
    }


def parse_month_or_current(value: str | None) -> tuple[int, int]:
    if not value:
        t: date = today_ist()
        return t.year, t.month
    m = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", value)
    if not m:
        raise ValueError("month must be YYYY-MM")
    return int(m.group(1)), int(m.group(2))
