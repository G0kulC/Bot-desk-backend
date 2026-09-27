from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

import pytest

from app.services.providers.base import InboundKind
from app.services.providers.meta_cloud import MetaCloudProvider

FIXTURES = Path(__file__).parent / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def sign(raw: bytes, secret: str = "test-app-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ parsing


def test_parse_text_message():
    events = MetaCloudProvider().parse_inbound(load("meta_text.json"))
    assert len(events) == 1
    ev = events[0]
    assert ev.kind == InboundKind.message
    assert ev.wa_id == "919876543210"
    assert ev.provider_message_id == "wamid.IN_TEXT_1"
    assert ev.body == "Hi, what is the cleaning price?"
    assert ev.msg_type == "text"
    assert ev.profile_name == "Ravi Kumar"
    assert ev.channel_ref == "PNID1"
    assert ev.timestamp is not None


def test_parse_non_text_messages():
    events = MetaCloudProvider().parse_inbound(load("meta_media.json"))
    types = [(e.msg_type, e.body) for e in events]
    assert types[0] == ("image", "My tooth")
    assert types[1] == ("audio", "[audio]")
    assert types[2][0] == "location" and "Anna Nagar Tower" in types[2][1] and "13.085,80.21" in types[2][1]
    assert types[3] == ("text", "Book now")  # interactive button reply is treated as text


def test_parse_statuses():
    events = MetaCloudProvider().parse_inbound(load("meta_status.json"))
    assert [e.kind for e in events] == [InboundKind.status] * 3
    assert [e.status for e in events] == ["delivered", "read", "failed"]
    assert "24 hours" in events[2].error


def test_parse_empty_payload():
    assert MetaCloudProvider().parse_inbound({}) == []


# ------------------------------------------------------------------ signature


def test_verify_signature_good_and_bad():
    p = MetaCloudProvider()
    raw = b'{"hello": "world"}'
    assert p.verify_signature(raw, {"X-Hub-Signature-256": sign(raw)}, None)
    assert not p.verify_signature(raw, {"X-Hub-Signature-256": sign(raw, "wrong")}, None)
    assert not p.verify_signature(raw, {"X-Hub-Signature-256": sign(b"tampered")}, None)
    assert not p.verify_signature(raw, {}, None)
    assert not p.verify_signature(raw, {"X-Hub-Signature-256": "md5=abc"}, None)


# ------------------------------------------------------------------ webhook routes


async def test_meta_get_challenge(api):
    r = await api.get(
        "/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": "verify-me", "hub.challenge": "12345"},
    )
    assert r.status_code == 200 and r.text == "12345"
    r = await api.get(
        "/webhooks/meta",
        params={"hub.mode": "subscribe", "hub.verify_token": "nope", "hub.challenge": "12345"},
    )
    assert r.status_code == 403


@pytest.mark.parametrize("header", [None, "sha256=deadbeef"])
async def test_meta_post_rejects_bad_signature(api, header):
    raw = json.dumps(load("meta_text.json")).encode()
    headers = {"Content-Type": "application/json"}
    if header:
        headers["X-Hub-Signature-256"] = header
    r = await api.post("/webhooks/meta", content=raw, headers=headers)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_signature"


async def test_meta_post_good_signature_stores_event(api, session):
    from sqlalchemy import select

    from app.models import WebhookEvent

    raw = json.dumps(load("meta_status.json")).encode()
    r = await api.post("/webhooks/meta", content=raw, headers={"X-Hub-Signature-256": sign(raw)})
    assert r.status_code == 200 and r.json() == {"ok": True, "duplicate": False}
    r = await api.post("/webhooks/meta", content=raw, headers={"X-Hub-Signature-256": sign(raw)})
    assert r.json()["duplicate"] is True
    rows = (await session.scalars(select(WebhookEvent))).all()
    assert len(rows) == 1 and rows[0].provider == "own" and rows[0].processed_at is not None
