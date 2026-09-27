from __future__ import annotations

import base64
import hashlib
import hmac
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import respx
from sqlalchemy import select

from app.models import Contact, Message, Provider, Sender
from app.security import encrypt_secret
from app.services.providers.aisensy import AUTH_HEADER, AiSensyProvider
from app.services.providers.base import InboundKind
from app.services.providers.factory import effective_provider, get_provider
from tests.helpers import OPENROUTER_URL, llm_response, model_reply
from tests.pipeline_setup import CUSTOMER, make_client

FIXTURES = Path(__file__).parent / "fixtures"
SEND_URL = "https://aisensy.test/project-apis/v1/project/proj_1/messages"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def sig(raw: bytes, secret: str = "aisensy-secret") -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


# ------------------------------------------------------------------ factory


def test_factory_env_default_vs_override(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    no_override = SimpleNamespace(provider_override=None)
    aisensy_override = SimpleNamespace(provider_override="aisensy")
    own_override = SimpleNamespace(provider_override=Provider.own)

    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "own")
    assert effective_provider(no_override) == Provider.own
    assert get_provider(no_override).name == "own"
    assert effective_provider(aisensy_override) == Provider.aisensy
    assert get_provider(aisensy_override).name == "aisensy"

    monkeypatch.setattr(settings, "WHATSAPP_PROVIDER", "aisensy")
    assert effective_provider(no_override) == Provider.aisensy
    assert get_provider(no_override).name == "aisensy"
    assert effective_provider(own_override) == Provider.own
    assert get_provider(own_override).name == "own"


# ------------------------------------------------------------------ parsing


def test_parse_inbound_text():
    [ev] = AiSensyProvider().parse_inbound(load("aisensy_inbound_text.json"))
    assert ev.kind == InboundKind.message and ev.provider == "aisensy"
    assert ev.wa_id == CUSTOMER and ev.provider_message_id == "aisensy.IN_1"
    assert ev.body == "Hi, is the clinic open on Sunday?" and ev.msg_type == "text"
    assert ev.profile_name == "Ravi" and ev.timestamp is not None and ev.timestamp.year == 2026


def test_parse_inbound_image():
    [ev] = AiSensyProvider().parse_inbound(load("aisensy_inbound_image.json"))
    assert ev.kind == InboundKind.message and ev.msg_type == "image" and ev.body == "[image]"


def test_parse_status():
    [ev] = AiSensyProvider().parse_inbound(load("aisensy_status.json"))
    assert (
        ev.kind == InboundKind.status
        and ev.status == "delivered"
        and ev.provider_message_id == "aisensy.OUT_1"
    )


def test_parse_agent_message_and_ignore_api_echo():
    [ev] = AiSensyProvider().parse_inbound(load("aisensy_agent.json"))
    assert ev.kind == InboundKind.agent_message and "Priya" in ev.body
    assert AiSensyProvider().parse_inbound(load("aisensy_echo.json")) == []


def test_parse_meta_shaped_forward():
    meta = json.loads((FIXTURES / "meta_text.json").read_text(encoding="utf-8"))
    [ev] = AiSensyProvider().parse_inbound(meta)
    assert ev.provider == "aisensy" and ev.channel_ref is None and ev.body.startswith("Hi")


# ------------------------------------------------------------------ signature


def test_signature_optional_without_secret_and_enforced_with_secret():
    p = AiSensyProvider()
    raw = b'{"a":1}'
    no_secret = SimpleNamespace(aisensy_webhook_secret_enc=None)
    with_secret = SimpleNamespace(aisensy_webhook_secret_enc=encrypt_secret("aisensy-secret"))
    assert p.verify_signature(raw, {}, no_secret)
    assert not p.verify_signature(raw, {}, with_secret)
    assert p.verify_signature(raw, {"X-AiSensy-Signature": sig(raw)}, with_secret)
    assert p.verify_signature(raw, {"x-aisensy-signature": "sha256=" + sig(raw)}, with_secret)
    b64 = base64.b64encode(hmac.new(b"aisensy-secret", raw, hashlib.sha256).digest()).decode()
    assert p.verify_signature(raw, {"X-AiSensy-Signature": b64}, with_secret)
    assert not p.verify_signature(raw, {"X-AiSensy-Signature": sig(raw, "wrong")}, with_secret)


# ------------------------------------------------------------------ sending


@respx.mock
async def test_send_text_uses_project_api():
    route = respx.post(SEND_URL).mock(
        return_value=httpx.Response(
            200, json={"messaging_product": "whatsapp", "messages": [{"id": "wamid.X"}]}
        )
    )
    channel = SimpleNamespace(aisensy_project_id="proj_1", aisensy_api_key_enc=encrypt_secret("pwd-123"))
    res = await AiSensyProvider().send_text(channel, CUSTOMER, "Hello")
    assert res.ok and res.provider_message_id == "wamid.X"
    req = route.calls[0].request
    assert req.headers[AUTH_HEADER] == "pwd-123"
    assert json.loads(req.content) == {
        "to": CUSTOMER,
        "type": "text",
        "recipient_type": "individual",
        "text": {"body": "Hello"},
    }


@respx.mock
async def test_send_error_reported():
    respx.post(SEND_URL).mock(return_value=httpx.Response(401, json={"message": "Invalid password"}))
    channel = SimpleNamespace(aisensy_project_id="proj_1", aisensy_api_key_enc=encrypt_secret("bad"))
    res = await AiSensyProvider().send_text(channel, CUSTOMER, "Hello")
    assert not res.ok and res.status_code == 401 and "Invalid password" in res.error


# ------------------------------------------------------------------ webhook route + pipeline


async def _post(api, name: str, token: str = "chan-token-1", secret: str = "aisensy-secret"):
    raw = json.dumps(load(name)).encode()
    return await api.post(
        f"/webhooks/aisensy/{token}", content=raw, headers={"X-AiSensy-Signature": sig(raw, secret)}
    )


async def test_webhook_rejects_unknown_token_and_bad_signature(api, session):
    await make_client(session, provider_override=Provider.aisensy)
    assert (await _post(api, "aisensy_status.json", token="nope")).status_code == 401
    assert (await _post(api, "aisensy_status.json", secret="wrong")).status_code == 401


@respx.mock
async def test_aisensy_end_to_end_reply(api, session):
    await make_client(session, provider_override=Provider.aisensy)
    send = respx.post(SEND_URL).mock(
        return_value=httpx.Response(200, json={"messages": [{"id": "aisensy.OUT_1"}]})
    )
    respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Yes, Sunday 10 AM – 1 PM.")))
    r = await _post(api, "aisensy_inbound_text.json")
    assert r.status_code == 200 and r.json()["duplicate"] is False
    bodies = [json.loads(c.request.content) for c in send.calls]
    assert bodies == [{"to": CUSTOMER, "type": "text", "recipient_type": "individual",
                       "text": {"body": "Yes, Sunday 10 AM – 1 PM."}}]  # fmt: skip
    bot = (await session.scalars(select(Message).where(Message.sender == Sender.bot))).all()
    assert len(bot) == 1 and bot[0].provider == Provider.aisensy

    # Delivery status for our reply.
    await _post(api, "aisensy_status.json")
    session.expire_all()
    msg = await session.scalar(select(Message).where(Message.provider_message_id == "aisensy.OUT_1"))
    assert msg.status.value == "delivered"


@respx.mock
async def test_aisensy_agent_message_is_takeover(api, session):
    await make_client(session, provider_override=Provider.aisensy)
    respx.post(SEND_URL).mock(return_value=httpx.Response(200, json={"messages": [{"id": "aisensy.OUT_7"}]}))
    ai = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply("Hi")))
    await _post(api, "aisensy_agent.json")
    session.expire_all()
    contact = await session.scalar(select(Contact).where(Contact.wa_id == CUSTOMER))
    assert contact.handoff_active is True
    agent = (await session.scalars(select(Message).where(Message.sender == Sender.agent))).all()
    assert len(agent) == 1 and "Priya" in agent[0].body

    # Customer writes next: bot stays silent because a human is talking.
    await _post(api, "aisensy_inbound_text.json")
    assert ai.call_count == 0
