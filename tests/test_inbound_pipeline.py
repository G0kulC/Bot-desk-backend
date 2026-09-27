from __future__ import annotations

import json

import httpx
import respx
from sqlalchemy import func, select

from app.models import ClientStatus, Contact, Lead, Message, MsgStatus, Sender, WebhookEvent
from tests.helpers import OPENROUTER_URL, llm_response, model_reply
from tests.pipeline_setup import (
    CUSTOMER,
    META_SEND_URL,
    OWNER,
    make_client,
    meta_ok,
    meta_text_payload,
    signed,
)


async def post_meta(api, body: str, msg_id: str, **kw) -> httpx.Response:
    raw, headers = signed(meta_text_payload(body, msg_id, **kw))
    r = await api.post("/webhooks/meta", content=raw, headers=headers)
    assert r.status_code == 200, r.text
    return r


def sent_bodies(route) -> list[dict]:
    return [json.loads(c.request.content) for c in route.calls]


async def messages(session, sender: Sender | None = None) -> list[Message]:
    stmt = select(Message).order_by(Message.created_at)
    if sender:
        stmt = stmt.where(Message.sender == sender)
    session.expire_all()
    return list((await session.scalars(stmt)).all())


async def contact(session) -> Contact:
    session.expire_all()
    return await session.scalar(select(Contact).where(Contact.wa_id == CUSTOMER))


@respx.mock
async def test_normal_reply(api, session):
    await make_client(session)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(
        return_value=llm_response(model_reply("Scaling costs ₹1,200. Want to book?"))
    )

    await post_meta(api, "cleaning price?", "wamid.A1")

    assert ai.call_count == 1
    bodies = sent_bodies(meta)
    # mark-read + reply
    assert {"messaging_product": "whatsapp", "status": "read", "message_id": "wamid.A1"} in bodies
    replies = [b for b in bodies if b.get("type") == "text"]
    assert len(replies) == 1 and replies[0]["to"] == CUSTOMER
    assert replies[0]["text"]["body"] == "Scaling costs ₹1,200. Want to book?"
    assert meta.calls[0].request.headers["Authorization"] == "Bearer EAAG-test-token"

    bot = await messages(session, Sender.bot)
    assert len(bot) == 1
    assert bot[0].status == MsgStatus.sent and bot[0].ai_model == "primary/model"
    assert bot[0].tokens_in == 900 and bot[0].cost_usd is not None and bot[0].latency_ms is not None
    c = await contact(session)
    assert c.profile_name == "Ravi" and c.last_inbound_at is not None and c.detected_language == "English"

    wh = await session.scalar(select(WebhookEvent))
    assert wh.processed_at is not None and wh.error is None


@respx.mock
async def test_history_is_sent_to_model(api, session):
    await make_client(session)
    respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Sure.")))
    await post_meta(api, "hello", "wamid.H1")
    await post_meta(api, "price of cleaning?", "wamid.H2")
    sent = json.loads(ai.calls[1].request.content)["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "hello" and sent[-1]["content"] == "price of cleaning?"


@respx.mock
async def test_lead_created_and_owner_alerted(api, session):
    await make_client(session)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    respx.post(OPENROUTER_URL).mock(
        return_value=llm_response(
            model_reply(
                "Thanks Ravi! Saturday 11 AM noted. The team will confirm on WhatsApp.",
                lead={"name": "Ravi", "phone": "", "need": "teeth cleaning", "when": "Saturday 11 AM"},
            )
        )
    )
    await post_meta(api, "I am Ravi, want cleaning on Saturday 11am", "wamid.L1")

    leads = (await session.scalars(select(Lead))).all()
    assert len(leads) == 1
    lead = leads[0]
    assert lead.name == "Ravi" and lead.need == "teeth cleaning" and lead.preferred_time == "Saturday 11 AM"
    assert lead.phone == f"+{CUSTOMER}"  # defaults to the WhatsApp number
    # Owner has not messaged in 24h -> approved template.
    templates = [b for b in sent_bodies(meta) if b.get("type") == "template"]
    assert len(templates) == 1
    t = templates[0]
    assert t["to"] == OWNER and t["template"]["name"] == "new_lead_alert"
    params = [p["text"] for p in t["template"]["components"][0]["parameters"]]
    assert params[0] == "Ravi" and params[1] == f"+{CUSTOMER}" and "teeth cleaning" in params[2]
    alerts = await messages(session, Sender.system)
    assert (
        len(alerts) == 1 and alerts[0].meta["alert_kind"] == "lead" and alerts[0].meta["undelivered"] is False
    )

    # The same lead again -> no duplicate lead, no second alert.
    await post_meta(api, "ok", "wamid.L2")
    assert (await session.scalar(select(func.count()).select_from(Lead))) == 1
    assert len(await messages(session, Sender.system)) == 1


@respx.mock
async def test_owner_alert_uses_text_inside_24h(api, session):
    client, _ = await make_client(session)
    session.add(Contact(client_id=client.id, wa_id=OWNER, last_inbound_at=func.now()))
    await session.commit()
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    respx.post(OPENROUTER_URL).mock(
        return_value=llm_response(
            model_reply("Noted!", lead={"name": "Ravi", "phone": "", "need": "RCT", "when": ""})
        )
    )
    await post_meta(api, "RCT please", "wamid.T1")
    to_owner = [b for b in sent_bodies(meta) if b.get("to") == OWNER]
    assert len(to_owner) == 1 and to_owner[0]["type"] == "text"
    assert "New lead" in to_owner[0]["text"]["body"]


@respx.mock
async def test_handoff_set_and_bot_silent_during_handoff(api, session):
    await make_client(session)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(
        return_value=llm_response(
            model_reply(
                "Sorry to hear that. A team member will call you.", handoff=True, handoff_reason="pain"
            )
        )
    )
    await post_meta(api, "I have severe tooth pain", "wamid.P1")
    c = await contact(session)
    assert c.handoff_active is True and c.handoff_reason == "pain" and c.handoff_since is not None
    alerts = await messages(session, Sender.system)
    assert [a.meta["alert_kind"] for a in alerts] == ["handoff"]

    calls_before = meta.call_count
    await post_meta(api, "hello??", "wamid.P2")
    assert ai.call_count == 1  # no AI call during handoff
    new_bodies = [json.loads(c.request.content) for c in meta.calls[calls_before:]]
    assert all(b.get("status") == "read" for b in new_bodies)  # only mark-read
    inbound = (await messages(session, Sender.customer))[-1]
    assert inbound.meta["skip_reason"] == "handoff_active"


@respx.mock
async def test_opted_out_contact_and_stop_keyword(api, session):
    await make_client(session)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi")))

    await post_meta(api, "STOP", "wamid.S1")
    c = await contact(session)
    assert c.opted_out is True
    confirmations = [b for b in sent_bodies(meta) if b.get("type") == "text"]
    assert len(confirmations) == 1 and "START" in confirmations[0]["text"]["body"]

    await post_meta(api, "what are your timings?", "wamid.S2")
    assert ai.call_count == 0
    assert len([b for b in sent_bodies(meta) if b.get("type") == "text"]) == 1
    assert (await messages(session, Sender.customer))[-1].meta["skip_reason"] == "opted_out"

    await post_meta(api, "நிறுத்து", "wamid.S3")  # Tamil STOP while already opted out: silent
    assert len([b for b in sent_bodies(meta) if b.get("type") == "text"]) == 1


@respx.mock
async def test_duplicate_webhook_ignored(api, session):
    from app.services.inbound import handle_event
    from app.services.providers.meta_cloud import MetaCloudProvider

    await make_client(session)
    respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi")))

    await post_meta(api, "hello", "wamid.D1")
    await post_meta(api, "hello", "wamid.D1")  # identical body: stored once
    # Same provider message id in a different body (Meta retry with new envelope): still ignored.
    ev = MetaCloudProvider().parse_inbound(meta_text_payload("hello", "wamid.D1", name="Ravi K"))[0]
    await handle_event(ev)

    assert ai.call_count == 1
    assert len(await messages(session, Sender.customer)) == 1
    assert len(await messages(session, Sender.bot)) == 1
    assert (await session.scalar(select(func.count()).select_from(WebhookEvent))) == 1


@respx.mock
async def test_fallback_model_used_on_failure(api, session):
    await make_client(session)
    respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(
        side_effect=[
            httpx.Response(500, json={"error": "boom"}),
            llm_response(model_reply("Hello from fallback")),
        ]
    )
    await post_meta(api, "hi", "wamid.F1")
    assert [json.loads(c.request.content)["model"] for c in ai.calls] == ["primary/model", "fallback/model"]
    bot = await messages(session, Sender.bot)
    assert bot[0].body == "Hello from fallback" and bot[0].meta["used_fallback"] is True


@respx.mock
async def test_both_models_fail_sends_polite_fallback_and_alerts(api, session):
    await make_client(session)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    respx.post(OPENROUTER_URL).mock(side_effect=httpx.ConnectTimeout("down"))
    await post_meta(api, "hi", "wamid.F2")
    texts = [b["text"]["body"] for b in sent_bodies(meta) if b.get("type") == "text"]
    assert texts == ["Thanks! Our team will reply shortly."]
    alerts = await messages(session, Sender.system)
    assert len(alerts) == 1 and alerts[0].meta["alert_kind"] == "ai_failed"


@respx.mock
async def test_invented_price_guardrail(api, session):
    await make_client(session)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    respx.post(OPENROUTER_URL).mock(
        return_value=llm_response(model_reply("Whitening is only ₹2,999 this week!"))
    )
    await post_meta(api, "whitening price?", "wamid.G1")
    texts = [b["text"]["body"] for b in sent_bodies(meta) if b.get("type") == "text"]
    assert texts == ["Let me confirm the exact price with the team and get back to you shortly."]
    c = await contact(session)
    assert c.handoff_active is True and "₹2,999" in c.handoff_reason
    bot = await messages(session, Sender.bot)
    assert any("price_not_in_knowledge" in n for n in bot[0].meta["guardrail_notes"])


@respx.mock
async def test_live_client_unapproved_knowledge_holds_and_alerts(api, session):
    await make_client(session, status=ClientStatus.live, approved=False)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi")))
    await post_meta(api, "hi", "wamid.K1")
    assert ai.call_count == 0
    texts = [b["text"]["body"] for b in sent_bodies(meta) if b.get("type") == "text"]
    assert texts == ["Thanks for your message! Our team will get back to you shortly."]
    alerts = await messages(session, Sender.system)
    assert alerts[0].meta["alert_kind"] == "kb_not_approved"


@respx.mock
async def test_trial_client_unapproved_knowledge_still_replies(api, session):
    await make_client(session, status=ClientStatus.trial, approved=False)
    respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi there")))
    await post_meta(api, "hi", "wamid.K2")
    assert ai.call_count == 1


@respx.mock
async def test_bot_disabled_and_paused_are_silent(api, session):
    client, _ = await make_client(session)
    client.bot_enabled = False
    await session.commit()
    respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi")))
    await post_meta(api, "hi", "wamid.B1")
    client.bot_enabled = True
    client.status = ClientStatus.paused
    await session.commit()
    await post_meta(api, "hi again", "wamid.B2")
    assert ai.call_count == 0
    reasons = [m.meta["skip_reason"] for m in await messages(session, Sender.customer)]
    assert reasons == ["bot_disabled", "client_paused"]


@respx.mock
async def test_non_text_message_gets_person_will_check_reply(api, session):
    from pathlib import Path

    await make_client(session)
    meta = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Sure, booking noted.")))
    payload = json.loads((Path(__file__).parent / "fixtures" / "meta_media.json").read_text(encoding="utf-8"))
    raw, headers = signed(payload)
    r = await api.post("/webhooks/meta", content=raw, headers=headers)
    assert r.status_code == 200
    texts = [b["text"]["body"] for b in sent_bodies(meta) if b.get("type") == "text"]
    # One acknowledgement for image/audio/location (deduplicated), then an AI reply to the button text.
    assert texts == ["Thanks! A team member will check this and reply soon.", "Sure, booking noted."]
    assert ai.call_count == 1
    types = [m.msg_type.value for m in await messages(session, Sender.customer)]
    assert types == ["image", "audio", "location", "text"]


@respx.mock
async def test_status_updates_applied(api, session):
    from pathlib import Path

    client, _ = await make_client(session)
    respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi")))
    c = Contact(client_id=client.id, wa_id=CUSTOMER)
    session.add(c)
    await session.flush()
    for mid in ("wamid.OUT_1", "wamid.OUT_2"):
        session.add(
            Message(
                client_id=client.id, contact_id=c.id, direction="out", sender=Sender.bot, provider="own",
                provider_message_id=mid, msg_type="text", body="x", status=MsgStatus.sent,
            )
        )  # fmt: skip
    await session.commit()
    payload = json.loads(
        (Path(__file__).parent / "fixtures" / "meta_status.json").read_text(encoding="utf-8")
    )
    raw, headers = signed(payload)
    await api.post("/webhooks/meta", content=raw, headers=headers)
    session.expire_all()
    m1 = await session.scalar(select(Message).where(Message.provider_message_id == "wamid.OUT_1"))
    m2 = await session.scalar(select(Message).where(Message.provider_message_id == "wamid.OUT_2"))
    assert m1.status == MsgStatus.read
    assert m2.status == MsgStatus.failed and "24 hours" in m2.error


@respx.mock
async def test_tamil_and_hindi_stop_keywords(api, session):
    await make_client(session)
    respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi")))
    await post_meta(api, "நிறுத்து!", "wamid.TS1")
    assert (await contact(session)).opted_out is True
    await post_meta(api, "START", "wamid.TS2")
    assert (await contact(session)).opted_out is False
    await post_meta(api, "रोको", "wamid.TS3")
    assert (await contact(session)).opted_out is True
    assert ai.call_count == 0
