from __future__ import annotations

import json

import httpx
import pytest
import respx

from app.services.ai.engine import (
    AIReply,
    apply_guardrails,
    check_prices,
    extract_json,
    generate_reply,
    parse_model_json,
    trim_words,
)
from app.services.ai.prompts import build_system_prompt, guess_language
from tests.helpers import DENTAL_CLIENT, DENTAL_KB, OPENROUTER_URL, llm_response, model_reply

GOOD = '{"reply": "Hi! How can I help?", "language": "English", "lead": null, "handoff": false, "handoff_reason": null}'


# ------------------------------------------------------------------ JSON parsing of messy output


@pytest.mark.parametrize(
    "raw",
    [
        GOOD,
        f"```json\n{GOOD}\n```",
        f"```\n{GOOD}\n```",
        f"Sure! Here is the reply:\n{GOOD}",
        f"{GOOD}\nHope this helps.",
        f"Text before ```json {GOOD} ``` and after",
    ],
)
def test_parse_messy_json(raw):
    r = parse_model_json(raw)
    assert r.reply == "Hi! How can I help?"
    assert r.handoff is False and r.lead is None


def test_parse_lead_and_string_bool():
    raw = json.dumps(
        {
            "reply": "Noted",
            "language": "Tamil",
            "lead": {"name": "Ravi", "phone": None, "need": "cleaning", "when": "Sat"},
            "handoff": "true",
        }
    )
    r = parse_model_json(raw)
    assert r.lead is not None and r.lead.name == "Ravi" and r.lead.phone == ""
    assert r.handoff is True and r.language == "Tamil"


def test_parse_empty_lead_becomes_none():
    raw = json.dumps({"reply": "Hi", "lead": {"name": "", "phone": "", "need": "", "when": ""}})
    assert parse_model_json(raw).lead is None


@pytest.mark.parametrize(
    "raw", ["no json here", "{not valid json}", '{"language": "English"}', '{"reply": "  "}', "[1,2]"]
)
def test_parse_failures(raw):
    with pytest.raises(ValueError):
        parse_model_json(raw)


def test_extract_json_nested_braces():
    assert extract_json('x {"a": {"b": 1}} y') == {"a": {"b": 1}}


# ------------------------------------------------------------------ guardrails


def test_price_check_passes_known_prices():
    assert check_prices("Scaling is ₹1,200 and consultation Rs. 300", DENTAL_KB.services) == []
    assert check_prices("Root canal starts from ₹4500", DENTAL_KB.services) == []


def test_price_check_flags_invented_price():
    assert check_prices("Whitening is ₹2,999 only!", DENTAL_KB.services) == ["₹2,999"]


def test_invented_price_replaced_and_handoff():
    reply = AIReply(reply="Whitening is just ₹2,999 today!", language="English")
    out, notes = apply_guardrails(reply, DENTAL_KB, 60)
    assert out.handoff is True
    assert "confirm the exact price" in out.reply
    assert any(n.startswith("price_not_in_knowledge") for n in notes)


def test_invented_price_tamil_reply():
    reply = AIReply(reply="விலை ₹999 மட்டும்", language="Tamil")
    out, _ = apply_guardrails(reply, DENTAL_KB, 60)
    assert out.handoff is True and "விலை" in out.reply


def test_unknown_link_and_phone_removed_known_kept():
    reply = AIReply(
        reply="Call +91 98400 12345 or 99999 88888. Map: https://maps.example.com/smile. Promo: https://spam.example.org/x",
    )
    out, notes = apply_guardrails(reply, DENTAL_KB, 60)
    assert "98400 12345" in out.reply
    assert "99999 88888" not in out.reply
    assert "https://maps.example.com/smile" in out.reply
    assert "spam.example.org" not in out.reply
    assert any("removed_links" in n for n in notes)
    assert any("removed_phone_numbers" in n for n in notes)


def test_customer_phone_repeat_allowed_via_extra_text():
    reply = AIReply(reply="Got it, we will call you on 9876543210.")
    out, _ = apply_guardrails(reply, DENTAL_KB, 60, extra_allowed_text="my number is 98765 43210")
    assert "9876543210" in out.reply


def test_trim_at_sentence_end():
    text = "This is the first sentence of the reply. " + " ".join(["word"] * 10) + ". Third one."
    trimmed, did = trim_words(text, 12)
    assert did and trimmed.endswith(".")
    assert len(trimmed.split()) <= 12


def test_trim_no_sentence_end_adds_ellipsis():
    trimmed, did = trim_words(" ".join(["word"] * 80), 60)
    assert did and trimmed.endswith("…") and len(trimmed.split()) == 60


def test_trim_short_untouched():
    assert trim_words("Short reply.", 60) == ("Short reply.", False)


# ------------------------------------------------------------------ prompt


def test_system_prompt_is_deterministic_and_filled():
    p1 = build_system_prompt(DENTAL_CLIENT, DENTAL_KB)
    p2 = build_system_prompt(DENTAL_CLIENT, DENTAL_KB)
    assert p1 == p2
    assert "You are the WhatsApp assistant for Smile Care Dental, a dental clinic in Chennai, India." in p1
    assert "Allowed reply languages: English, Tamil." in p1
    assert "Scaling & polishing: ₹1,200" in p1
    assert '{"reply": "...", "language": "Tamil|English|Tanglish|..."' in p1
    assert "{address}" not in p1


def test_guess_language():
    assert guess_language("வணக்கம்") == "Tamil"
    assert guess_language("नमस्ते") == "Hindi"
    assert guess_language("hello", "Tanglish") == "Tanglish"


# ------------------------------------------------------------------ engine + fallback


@respx.mock
async def test_engine_primary_ok():
    route = respx.post(OPENROUTER_URL).mock(return_value=llm_response(model_reply()))
    res = await generate_reply(DENTAL_CLIENT, DENTAL_KB, [], "cleaning price?")
    assert res.ok and not res.used_fallback
    assert res.reply.reply.startswith("Scaling costs ₹1,200")
    sent = json.loads(route.calls[0].request.content)
    assert sent["model"] == "primary/model"
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][-1] == {"role": "user", "content": "cleaning price?"}


@respx.mock
async def test_engine_falls_back_on_5xx():
    route = respx.post(OPENROUTER_URL).mock(
        side_effect=[httpx.Response(503, json={"error": "down"}), llm_response(model_reply())]
    )
    res = await generate_reply(DENTAL_CLIENT, DENTAL_KB, [], "hi")
    assert res.ok and res.used_fallback
    assert json.loads(route.calls[1].request.content)["model"] == "fallback/model"


@respx.mock
async def test_engine_falls_back_on_timeout_and_bad_json():
    respx.post(OPENROUTER_URL).mock(side_effect=httpx.ReadTimeout("slow"))
    res = await generate_reply(DENTAL_CLIENT, DENTAL_KB, [], "hi")
    assert not res.ok and len(res.errors) == 2

    bad = {"choices": [{"message": {"content": "I cannot answer in JSON"}}], "usage": {}}
    respx.post(OPENROUTER_URL).mock(side_effect=[llm_response(bad), llm_response(model_reply())])
    res = await generate_reply(DENTAL_CLIENT, DENTAL_KB, [], "hi")
    assert res.ok and res.used_fallback


# ------------------------------------------------------------------ test-chat endpoint


@respx.mock
async def test_test_chat_endpoint(api, auth):
    r = await api.post(
        "/api/v1/clients",
        json={"name": "Smile Care", "niche": "dental_clinic", "languages": ["English", "Tamil"]},
        headers=auth,
    )
    cid = r.json()["id"]
    r = await api.post(f"/api/v1/clients/{cid}/test-chat", json={"message": "hi"}, headers=auth)
    assert r.status_code == 409

    await api.put(
        f"/api/v1/clients/{cid}/knowledge", json={"services": "Scaling: ₹1,200", "faqs": ""}, headers=auth
    )
    respx.post(OPENROUTER_URL).mock(
        return_value=llm_response(
            model_reply(
                "Whitening is ₹5,000.", lead={"name": "Anu", "phone": "", "need": "whitening", "when": ""}
            )
        )
    )
    r = await api.post(
        f"/api/v1/clients/{cid}/test-chat",
        json={
            "history": [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "Hi!"}],
            "message": "whitening?",
        },
        headers=auth,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["handoff"] is True
    assert body["lead"]["name"] == "Anu"
    assert body["tokens_in"] == 900 and body["model"] == "primary/model"
    assert body["cost_inr"] == "0.0088"
    assert any("knowledge_not_approved" in n for n in body["guardrail_notes"])
    assert any("price_not_in_knowledge" in n for n in body["guardrail_notes"])

    r = await api.get(f"/api/v1/clients/{cid}/knowledge/export", headers=auth)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "Scaling: ₹1,200" in r.text
