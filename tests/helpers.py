from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

OPENROUTER_URL = "https://openrouter.test/api/v1/chat/completions"

DENTAL_KB = SimpleNamespace(
    address="14 Shanthi Colony, Anna Nagar, Chennai. https://maps.example.com/smile",
    timings="Mon–Sat 10 AM – 9 PM",
    services="Consultation: ₹300\nScaling & polishing: ₹1,200\nRoot canal: from ₹4,500",
    faqs="Q: Parking? A: Yes, two-wheeler parking.",
    booking_instructions="Collect name, problem, preferred time.",
    rules="Never diagnose.",
    handoff_contact="Front desk: +91 98400 12345",
    tone="Warm",
    approved=True,
)

DENTAL_CLIENT = SimpleNamespace(
    name="Smile Care Dental",
    niche="dental_clinic",
    city="Chennai",
    languages=["English", "Tamil"],
)


def model_reply(
    reply: str = "Scaling costs ₹1,200. Would you like to book?",
    language: str = "English",
    lead: dict | None = None,
    handoff: bool = False,
    handoff_reason: str | None = None,
    *,
    wrap: str = "{}",
    cost: float = 0.0001,
) -> dict:
    content = json.dumps(
        {
            "reply": reply,
            "language": language,
            "lead": lead,
            "handoff": handoff,
            "handoff_reason": handoff_reason,
        },
        ensure_ascii=False,
    )
    return {
        "id": "gen-1",
        "model": "primary/model",
        "choices": [{"message": {"role": "assistant", "content": wrap.replace("{}", content)}}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 60, "cost": cost},
    }


def llm_response(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)
