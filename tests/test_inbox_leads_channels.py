from __future__ import annotations

import json
from datetime import timedelta

import respx
from sqlalchemy import select

from app.models import Contact, Direction, Message, MsgStatus, Sender
from app.timeutil import utcnow
from tests.pipeline_setup import CUSTOMER, META_SEND_URL, OWNER, make_client, meta_ok

API = "/api/v1"


async def _seed_conversation(session, *, hours_ago: float = 1, handoff: bool = False):
    client, _ = await make_client(session)
    contact = Contact(
        client_id=client.id,
        wa_id=CUSTOMER,
        profile_name="Ravi",
        last_inbound_at=utcnow() - timedelta(hours=hours_ago),
        handoff_active=handoff,
    )
    session.add(contact)
    await session.flush()
    base = utcnow() - timedelta(hours=hours_ago)
    for i, (direction, sender, body) in enumerate(
        [
            (Direction.inbound, Sender.customer, "hello"),
            (Direction.outbound, Sender.bot, "Hi! How can I help?"),
            (Direction.inbound, Sender.customer, "cleaning price?"),
        ]
    ):
        session.add(
            Message(
                client_id=client.id,
                contact_id=contact.id,
                direction=direction,
                sender=sender,
                provider="own",
                msg_type="text",
                body=body,
                status=MsgStatus.received if direction == Direction.inbound else MsgStatus.sent,
                created_at=base + timedelta(seconds=i),
            )
        )
    await session.commit()
    return client, contact


async def test_inbox_list_and_filters(api, auth, session):
    _, contact = await _seed_conversation(session, handoff=True)
    r = await api.get(f"{API}/inbox", headers=auth)
    assert r.status_code == 200, r.text
    [item] = r.json()
    assert item["contact_id"] == str(contact.id)
    assert item["unread_count"] == 2
    assert item["last_message_preview"] == "cleaning price?"
    assert item["can_reply"] is True and item["client_name"] == "Smile Care Dental"

    assert len((await api.get(f"{API}/inbox", params={"handoff": "false"}, headers=auth)).json()) == 0
    assert len((await api.get(f"{API}/inbox", params={"handoff": "true"}, headers=auth)).json()) == 1
    assert len((await api.get(f"{API}/inbox", params={"q": "ravi"}, headers=auth)).json()) == 1
    assert len((await api.get(f"{API}/inbox", params={"q": "nobody"}, headers=auth)).json()) == 0

    # Reading the thread clears unread.
    r = await api.get(f"{API}/contacts/{contact.id}/messages", headers=auth)
    msgs = r.json()
    assert [m["body"] for m in msgs] == ["hello", "Hi! How can I help?", "cleaning price?"]
    r = await api.get(f"{API}/inbox", headers=auth)
    assert r.json()[0]["unread_count"] == 0

    # Pagination with `before`.
    r = await api.get(
        f"{API}/contacts/{contact.id}/messages",
        params={"before": msgs[2]["created_at"], "limit": 1},
        headers=auth,
    )
    assert [m["body"] for m in r.json()] == ["Hi! How can I help?"]


@respx.mock
async def test_agent_reply_inside_window(api, auth, session):
    _, contact = await _seed_conversation(session)
    route = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    r = await api.post(
        f"{API}/contacts/{contact.id}/reply", json={"body": "Hi Ravi, it is ₹1,200."}, headers=auth
    )
    assert r.status_code == 200, r.text
    assert r.json()["sender"] == "agent" and r.json()["status"] == "sent"
    assert json.loads(route.calls[0].request.content)["text"]["body"] == "Hi Ravi, it is ₹1,200."
    contact_id = contact.id
    session.expire_all()
    c = await session.get(Contact, contact_id)
    assert c.handoff_active is True  # bot pauses while a person is talking


async def test_agent_reply_outside_window_409(api, auth, session):
    _, contact = await _seed_conversation(session, hours_ago=30)
    r = await api.post(f"{API}/contacts/{contact.id}/reply", json={"body": "Hello?"}, headers=auth)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "outside_24h_window"


@respx.mock
async def test_agent_reply_provider_failure_502(api, auth, session):
    import httpx

    _, contact = await _seed_conversation(session)
    respx.post(META_SEND_URL).mock(
        return_value=httpx.Response(400, json={"error": {"message": "bad", "code": 100}})
    )
    r = await api.post(f"{API}/contacts/{contact.id}/reply", json={"body": "Hi"}, headers=auth)
    assert r.status_code == 502
    failed = await session.scalar(select(Message).where(Message.sender == Sender.agent))
    assert failed.status == MsgStatus.failed


async def test_handoff_and_opt_out_toggles(api, auth, session):
    _, contact = await _seed_conversation(session)
    r = await api.post(f"{API}/contacts/{contact.id}/handoff", json={"active": True}, headers=auth)
    assert r.json()["handoff_active"] is True and r.json()["handoff_since"]
    r = await api.post(f"{API}/contacts/{contact.id}/handoff", json={"active": False}, headers=auth)
    assert r.json()["handoff_active"] is False and r.json()["handoff_since"] is None
    r = await api.post(f"{API}/contacts/{contact.id}/opt-out", json={"opted_out": True}, headers=auth)
    assert r.json()["opted_out"] is True


async def test_leads_crud(api, auth, session):
    client, contact = await _seed_conversation(session)
    r = await api.post(
        f"{API}/leads",
        json={"client_id": str(client.id), "contact_id": str(contact.id), "name": "Ravi", "need": "RCT"},
        headers=auth,
    )
    assert r.status_code == 201, r.text
    lead = r.json()
    assert lead["status"] == "new"
    r = await api.patch(f"{API}/leads/{lead['id']}", json={"status": "won", "notes": "Paid"}, headers=auth)
    assert r.json()["status"] == "won" and r.json()["notes"] == "Paid"
    assert len((await api.get(f"{API}/leads", params={"status": "won"}, headers=auth)).json()) == 1
    assert len((await api.get(f"{API}/leads", params={"status": "new"}, headers=auth)).json()) == 0
    assert (
        len((await api.get(f"{API}/leads", params={"client_id": str(client.id)}, headers=auth)).json()) == 1
    )


@respx.mock
async def test_channel_put_get_masks_secrets_and_test_send(api, auth, session):
    r = await api.post(
        f"{API}/clients", json={"name": "Glow Studio", "owner_phone": f"+{OWNER}"}, headers=auth
    )
    cid = r.json()["id"]
    r = await api.put(
        f"{API}/clients/{cid}/channel",
        json={
            "meta_phone_number_id": "PNID1",
            "meta_access_token": "EAAG-secret-9876",
            "display_phone": "9840000001",
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text
    ch = r.json()
    assert ch["meta_access_token"] == {"has_token": True, "last4": "9876"}
    assert "EAAG-secret" not in r.text
    assert ch["webhook_url"] == "https://api.test/webhooks/meta"
    assert ch["display_phone"] == "+919840000001"

    # Switching the client to AiSensy changes the webhook URL to the per-channel token URL.
    await api.patch(f"{API}/clients/{cid}", json={"provider_override": "aisensy"}, headers=auth)
    r = await api.get(f"{API}/clients/{cid}/channel", headers=auth)
    assert r.json()["webhook_url"].startswith("https://api.test/webhooks/aisensy/")

    await api.patch(f"{API}/clients/{cid}", json={"provider_override": "own"}, headers=auth)
    route = respx.post(META_SEND_URL).mock(side_effect=meta_ok)
    r = await api.post(f"{API}/clients/{cid}/channel/test", headers=auth)
    assert r.status_code == 200 and r.json()["ok"] is True
    sent = json.loads(route.calls[0].request.content)
    assert sent["to"] == OWNER and sent["text"]["body"] == "Bot Desk test message ✅"
