from __future__ import annotations

import re
from typing import Protocol

# Tuned wording – keep it as is. Placeholders are replaced in a single pass (see build_system_prompt),
# so braces inside the JSON example and inside business content are never treated as placeholders.
SYSTEM_PROMPT_TEMPLATE = """You are the WhatsApp assistant for {client.name}, a {niche} in {city}, India. You are chatting with a customer on WhatsApp.

BUSINESS INFORMATION (the only facts you may use):
Address: {address}
Timings: {timings}
Services and prices:
{services}
Common questions:
{faqs}
Booking / orders: {booking_instructions}
Rules: {rules}
Tone: {tone}

LANGUAGE:
- Allowed reply languages: {languages}. Detect the customer's language and script. If it is allowed, reply in the same language and script (Tamil script → Tamil script; Tanglish/Hinglish in Latin letters → the same style). Otherwise reply in English.

HOW TO REPLY:
- Sound like a helpful front-desk person: warm, short, at most 3 short lines, at most one emoji.
- Use prices exactly as listed. For "from" prices, say "starts from". Never invent prices, offers, discounts, doctors, staff names, time slots or availability.
- Never give medical, legal or financial advice. Never diagnose, suggest medicines or promise results.
- If asked something not covered above, say a team member will confirm, and set handoff true.
- To book or order, collect the details listed under Booking one or two at a time. When you have enough, repeat them back and say the team will confirm on WhatsApp.
- Set handoff true for: emergencies, pain or health symptoms, complaints or anger, requests for the owner or a person, bulk or custom quotes, or anything you are unsure about.

OUTPUT: reply with ONLY one JSON object, no other text:
{"reply": "...", "language": "Tamil|English|Tanglish|...", "lead": null or {"name": "", "phone": "", "need": "", "when": ""}, "handoff": false, "handoff_reason": null}
Set "lead" once the customer has given at least a name or a clear booking need. Use "" for unknown fields."""

_PLACEHOLDER_RE = re.compile(
    r"\{(client\.name|niche|city|address|timings|services|faqs|booking_instructions|rules|tone|languages)\}"
)

NICHE_LABELS = {
    "dental_clinic": "dental clinic",
    "skin_clinic": "skin clinic",
    "salon": "salon",
    "coaching_centre": "coaching centre",
    "gym": "gym",
    "bakery_sweets": "bakery and sweet shop",
    "real_estate": "real-estate agency",
    "restaurant": "restaurant",
    "other": "local business",
}


class _ClientLike(Protocol):
    name: str
    niche: object
    city: str
    languages: list[str]


class _KnowledgeLike(Protocol):
    address: str
    timings: str
    services: str
    faqs: str
    booking_instructions: str
    rules: str
    tone: str


def _v(value: str | None) -> str:
    value = (value or "").strip()
    return value if value else "Not provided"


def build_system_prompt(client: _ClientLike, kb: _KnowledgeLike) -> str:
    """Deterministic for a given client + knowledge, so provider-side prompt caching can work."""
    niche = getattr(client.niche, "value", client.niche)
    values = {
        "client.name": client.name,
        "niche": NICHE_LABELS.get(str(niche), str(niche).replace("_", " ")),
        "city": client.city or "India",
        "address": _v(kb.address),
        "timings": _v(kb.timings),
        "services": _v(kb.services),
        "faqs": _v(kb.faqs),
        "booking_instructions": _v(kb.booking_instructions),
        "rules": _v(kb.rules),
        "tone": _v(kb.tone) if kb.tone else "Warm, polite and short.",
        "languages": ", ".join(client.languages or ["English"]),
    }
    return _PLACEHOLDER_RE.sub(lambda m: values[m.group(1)], SYSTEM_PROMPT_TEMPLATE)


# Short fixed messages the bot sends without the model, per language.
CANNED: dict[str, dict[str, str]] = {
    "fallback": {
        "English": "Thanks! Our team will reply shortly.",
        "Tamil": "நன்றி! எங்கள் குழு விரைவில் பதில் அளிக்கும்.",
        "Tanglish": "Thanks! Engal team seekiram reply pannuvanga.",
        "Hindi": "धन्यवाद! हमारी टीम जल्द ही जवाब देगी।",
        "Hinglish": "Thanks! Hamari team jaldi reply karegi.",
    },
    "price_confirm": {
        "English": "Let me confirm the exact price with the team and get back to you shortly.",
        "Tamil": "சரியான விலையை எங்கள் குழுவிடம் உறுதி செய்து விரைவில் சொல்கிறோம்.",
        "Tanglish": "Exact price-ah team kitta confirm panni seekiram solrom.",
        "Hindi": "सही कीमत टीम से पक्का करके जल्द ही बताते हैं।",
        "Hinglish": "Exact price team se confirm karke jaldi batate hain.",
    },
    "holding": {
        "English": "Thanks for your message! Our team will get back to you shortly.",
        "Tamil": "உங்கள் செய்திக்கு நன்றி! எங்கள் குழு விரைவில் தொடர்பு கொள்ளும்.",
        "Tanglish": "Message-ku thanks! Engal team seekiram contact pannuvanga.",
        "Hindi": "आपके संदेश के लिए धन्यवाद! हमारी टीम जल्द संपर्क करेगी।",
        "Hinglish": "Message ke liye thanks! Hamari team jaldi contact karegi.",
    },
    "non_text": {
        "English": "Thanks! A team member will check this and reply soon.",
        "Tamil": "நன்றி! எங்கள் குழுவினர் இதைப் பார்த்து விரைவில் பதில் அளிப்பார்கள்.",
        "Tanglish": "Thanks! Engal team idha paathutu seekiram reply pannuvanga.",
        "Hindi": "धन्यवाद! हमारी टीम इसे देखकर जल्द जवाब देगी।",
        "Hinglish": "Thanks! Hamari team ise dekh kar jaldi reply karegi.",
    },
    "opt_out": {
        "English": "Done. You won't get automated replies from us any more. Send START anytime to chat again.",
        "Tamil": "சரி. இனி தானியங்கி பதில்கள் அனுப்பப்படாது. மீண்டும் பேச START என்று அனுப்பவும்.",
        "Tanglish": "Sari. Ini automated replies varadhu. Marubadiyum pesa START anuppunga.",
        "Hindi": "ठीक है। अब आपको स्वचालित संदेश नहीं मिलेंगे। फिर से बात करने के लिए START भेजें।",
        "Hinglish": "Theek hai. Ab automated replies nahi aayenge. Dobara baat karne ke liye START bhejein.",
    },
    "opt_in": {
        "English": "Welcome back! How can we help you today?",
        "Tamil": "மீண்டும் வருக! இன்று உங்களுக்கு எப்படி உதவலாம்?",
        "Tanglish": "Welcome back! Ungalukku eppadi help pannalam?",
        "Hindi": "फिर से स्वागत है! आज हम आपकी कैसे मदद करें?",
        "Hinglish": "Welcome back! Aaj hum aapki kaise madad karein?",
    },
}


def canned(key: str, language: str | None) -> str:
    options = CANNED[key]
    return options.get(language or "English", options["English"])


_TAMIL_RE = re.compile(r"[஀-௿]")
_DEVANAGARI_RE = re.compile(r"[ऀ-ॿ]")


def guess_language(text: str | None, fallback: str | None = None) -> str:
    """Cheap script check for canned replies sent without the model."""
    text = text or ""
    if _TAMIL_RE.search(text):
        return "Tamil"
    if _DEVANAGARI_RE.search(text):
        return "Hindi"
    return fallback or "English"
