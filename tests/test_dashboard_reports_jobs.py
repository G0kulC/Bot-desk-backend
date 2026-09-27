from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.jobs.tasks import build_attention_items, purge_old_webhook_payloads, release_stale_handoffs
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
    PaymentMethod,
    PaymentType,
    Sender,
    WebhookEvent,
)
from app.services.reports import normalise_question
from app.timeutil import IST, today_ist, utcnow
from tests.pipeline_setup import make_client

API = "/api/v1"


def ist(y, m, d, h, mi=0) -> datetime:
    return datetime(y, m, d, h, mi, tzinfo=IST).astimezone(UTC)


def msg(client, contact, sender, body, at, **kw) -> Message:
    direction = Direction.inbound if sender == Sender.customer else Direction.outbound
    return Message(
        client_id=client.id,
        contact_id=contact.id,
        direction=direction,
        sender=sender,
        provider="own",
        msg_type="text",
        body=body,
        status=MsgStatus.received if direction == Direction.inbound else MsgStatus.sent,
        created_at=at,
        **kw,
    )


def test_normalise_question():
    assert normalise_question("  What is the PRICE?? ") == "what is the price"
    assert normalise_question("விலை என்ன?") == "விலை என்ன"


async def test_monthly_report(api, auth, session):
    client, _ = await make_client(session)
    a = Contact(client_id=client.id, wa_id="911111111111", detected_language="Tamil")
    b = Contact(client_id=client.id, wa_id="912222222222", detected_language="English")
    session.add_all([a, b])
    await session.flush()
    session.add_all(
        [
            # Contact A: day message, bot reply after 4s, night message (23:30 IST), agent reply.
            msg(client, a, Sender.customer, "Price?", ist(2026, 8, 3, 11, 0)),
            msg(client, a, Sender.bot, "₹1,200", ist(2026, 8, 3, 11, 0) + timedelta(seconds=4),
                cost_usd=Decimal("0.0005"), ai_model="m"),
            msg(client, a, Sender.customer, "Timings?", ist(2026, 8, 3, 23, 30)),
            msg(client, a, Sender.bot, "10 to 9", ist(2026, 8, 3, 23, 30) + timedelta(seconds=6),
                cost_usd=Decimal("0.0005"), ai_model="m"),
            msg(client, a, Sender.agent, "Hi, Priya here", ist(2026, 8, 4, 10, 0)),
            msg(client, a, Sender.system, "alert", ist(2026, 8, 4, 10, 0), meta={"kind": "owner_alert",
                                                                             "alert_kind": "handoff"}),
            # Contact B: early morning (06:00 IST, night), same question as A.
            msg(client, b, Sender.customer, "price ?", ist(2026, 8, 20, 6, 0)),
            # Outside the month (IST): 1 Sep 00:30 IST is still 31 Aug in UTC.
            msg(client, b, Sender.customer, "September message", ist(2026, 9, 1, 0, 30)),
        ]
    )  # fmt: skip
    session.add(Lead(client_id=client.id, contact_id=a.id, name="A", created_at=ist(2026, 8, 3, 12)))
    await session.commit()

    r = await api.get(
        f"{API}/reports/monthly", params={"client_id": str(client.id), "month": "2026-08"}, headers=auth
    )
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["chats"] == 2
    assert rep["messages_in"] == 3
    assert rep["bot_replies"] == 2 and rep["agent_replies"] == 1 and rep["messages_out"] == 3
    assert rep["leads"] == 1 and rep["handoffs"] == 1
    assert rep["night_enquiries"] == 2 and rep["night_share"] == 0.667
    assert rep["top_questions"][0] == {"question": "price", "count": 2}
    assert rep["languages"] == {"Tamil": 1, "English": 1}
    assert rep["avg_bot_reply_seconds"] == 5.0
    assert rep["ai_cost_inr"] == "0.09"

    r = await api.get(
        f"{API}/reports/monthly", params={"client_id": str(client.id), "month": "2026-13"}, headers=auth
    )
    assert r.status_code == 422


async def test_dashboard_summary(api, auth, session):
    today = today_ist()
    live, _ = await make_client(session, status=ClientStatus.live)
    live.live_date = today - timedelta(days=40)  # current period unpaid -> overdue
    live.monthly_fee = Decimal("3999")
    trial = Client(name="Trial Salon", status=ClientStatus.trial, trial_start=today - timedelta(days=2))
    session.add(trial)
    session.add(
        Payment(
            client_id=live.id,
            type=PaymentType.setup,
            amount=Decimal("7999"),
            paid_on=today,
            method=PaymentMethod.upi,
        )
    )
    await session.commit()

    r = await api.get(f"{API}/dashboard/summary", headers=auth)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["paying_clients"] == 1 and d["goal"] == 10
    assert d["mrr"] == "3999.00"
    assert d["collected_this_month"] == "7999.00"
    assert d["overdue_count"] == 1 and d["overdue_amount"] == "3999.00"
    assert d["trials_ending_7d"] == 1


async def test_attention_job_and_resolve(api, auth, session):
    today = today_ist()
    live, channel = await make_client(session, status=ClientStatus.live)
    live.live_date = today - timedelta(days=40)
    channel.created_at = utcnow() - timedelta(days=10)
    trial = Client(name="Trial Gym", status=ClientStatus.trial, trial_start=today - timedelta(days=6))
    session.add(trial)
    await session.commit()

    await build_attention_items(session, today)
    kinds = sorted(i.kind for i in (await session.scalars(select(AttentionItem))).all())
    assert kinds == ["channel_silent", "payment_overdue", "trial_ending"]

    # Running again does not duplicate.
    await build_attention_items(session, today)
    assert len((await session.scalars(select(AttentionItem))).all()) == 3

    r = await api.get(f"{API}/dashboard/summary", headers=auth)
    attention = r.json()["attention"]
    assert {a["kind"] for a in attention} >= {"channel_silent", "payment_overdue", "trial_ending"}
    item_id = next(a["id"] for a in attention if a["kind"] == "trial_ending")
    r = await api.post(f"{API}/dashboard/attention/{item_id}/resolve", headers=auth)
    assert r.status_code == 200
    r = await api.get(f"{API}/dashboard/summary", headers=auth)
    assert "trial_ending" not in {a["kind"] for a in r.json()["attention"]}

    # Paying clears the payment item on the next run.
    prev = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    for month in (prev, date(today.year, today.month, 1)):  # current period may start last month
        session.add(
            Payment(client_id=live.id, type=PaymentType.monthly, amount=Decimal("1999"),
                    for_month=month, paid_on=today, method=PaymentMethod.cash)
        )  # fmt: skip
    await session.commit()
    await build_attention_items(session, today)
    open_kinds = {
        i.kind
        for i in (
            await session.scalars(select(AttentionItem).where(AttentionItem.resolved_at.is_(None)))
        ).all()
    }
    assert "payment_overdue" not in open_kinds


async def test_undelivered_alert_in_attention(api, auth, session):
    client, _ = await make_client(session)
    c = Contact(client_id=client.id, wa_id="911111111111")
    session.add(c)
    await session.flush()
    session.add(
        Message(client_id=client.id, contact_id=c.id, direction=Direction.outbound, sender=Sender.system,
                msg_type="template", body="alert", status=MsgStatus.failed, error="Template not approved",
                meta={"kind": "owner_alert", "alert_kind": "lead", "undelivered": True})
    )  # fmt: skip
    await session.commit()
    r = await api.get(f"{API}/dashboard/summary", headers=auth)
    und = [a for a in r.json()["attention"] if a["kind"] == "alert_undelivered"]
    assert len(und) == 1 and "Template not approved" in und[0]["text"]


async def test_release_stale_handoffs(session):
    client, _ = await make_client(session)
    stale = Contact(
        client_id=client.id,
        wa_id="911111111111",
        handoff_active=True,
        handoff_since=utcnow() - timedelta(hours=20),
    )
    fresh = Contact(
        client_id=client.id,
        wa_id="912222222222",
        handoff_active=True,
        handoff_since=utcnow() - timedelta(hours=20),
    )
    session.add_all([stale, fresh])
    await session.flush()
    session.add(msg(client, stale, Sender.agent, "old", utcnow() - timedelta(hours=13)))
    session.add(msg(client, fresh, Sender.customer, "still here", utcnow() - timedelta(hours=1)))
    # A recent bot/system message must not keep the handoff alive.
    session.add(msg(client, stale, Sender.system, "alert", utcnow() - timedelta(minutes=5)))
    await session.commit()
    stale_id, fresh_id = stale.id, fresh.id

    assert await release_stale_handoffs(session) == 1
    session.expire_all()
    assert (await session.get(Contact, stale_id)).handoff_active is False
    assert (await session.get(Contact, fresh_id)).handoff_active is True


async def test_purge_old_payloads(session):
    session.add_all(
        [
            WebhookEvent(
                provider="own", event_key="old", payload={"a": 1}, received_at=utcnow() - timedelta(days=31)
            ),
            WebhookEvent(
                provider="own", event_key="new", payload={"a": 2}, received_at=utcnow() - timedelta(days=1)
            ),
        ]
    )
    await session.commit()
    assert await purge_old_webhook_payloads(session) == 1
    session.expire_all()
    rows = {e.event_key: e.payload for e in (await session.scalars(select(WebhookEvent))).all()}
    assert rows == {"old": None, "new": {"a": 2}}


def test_scheduler_jobs_registered():
    from app.jobs.scheduler import build_scheduler

    sched = build_scheduler()
    assert {j.id for j in sched.get_jobs()} == {"release_handoffs", "daily_attention", "purge_payloads"}


async def test_dashboard_pipeline_and_live_attention(api, auth, session):
    today = today_ist()
    live, _ = await make_client(session, status=ClientStatus.live)
    live.live_date = today - timedelta(days=40)
    live.setup_fee = Decimal("3999")
    session.add(Client(name="Lead Co", status=ClientStatus.lead))
    session.add(Contact(client_id=live.id, wa_id="911111111111", handoff_active=True))
    await session.commit()
    r = await api.get(f"{API}/dashboard/summary", headers=auth)
    d = r.json()
    assert d["pipeline"] == {"lead": 1, "trial": 0, "live": 1, "paused": 0}
    kinds = {a["kind"] for a in d["attention"]}
    assert {"payment_overdue", "setup_unpaid", "handoff_waiting"} <= kinds
    waiting = next(a for a in d["attention"] if a["kind"] == "handoff_waiting")
    assert "1 chat is waiting" in waiting["text"] and waiting["client_id"] == str(live.id)

    r = await api.get(f"{API}/billing/renewals", headers=auth)
    assert r.json()[0]["package"] == "starter" and "setup_fee" in r.json()[0]
