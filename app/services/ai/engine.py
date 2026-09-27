"""AI engine: build the prompt, call the model (with fallback), parse JSON, apply guardrails.

Used by both the live inbound pipeline and the test-chat simulator, so behaviour is identical.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

from app.config import get_settings
from app.services.ai.openrouter import LLMError, chat_completion
from app.services.ai.prompts import build_system_prompt, canned

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- model output schema


class LeadInfo(BaseModel):
    name: str = ""
    phone: str = ""
    need: str = ""
    when: str = ""

    @field_validator("name", "phone", "need", "when", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> str:
        return "" if v is None else str(v).strip()

    def is_empty(self) -> bool:
        return not any((self.name, self.phone, self.need, self.when))


class AIReply(BaseModel):
    reply: str
    language: str = "English"
    lead: LeadInfo | None = None
    handoff: bool = False
    handoff_reason: str | None = None

    @field_validator("reply")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("reply is empty")
        return v.strip()

    @field_validator("language", mode="before")
    @classmethod
    def _lang(cls, v: Any) -> str:
        return str(v).strip() if v else "English"

    @field_validator("handoff", mode="before")
    @classmethod
    def _bool(cls, v: Any) -> bool:
        if isinstance(v, str):
            return v.strip().lower() in {"true", "yes", "1"}
        return bool(v)


_FENCE_RE = re.compile(r"```(?:json|JSON)?")


def extract_json(text: str) -> dict:
    """Tolerant JSON extraction: strip code fences, take the first '{' to the last '}'."""
    cleaned = _FENCE_RE.sub("", text or "")
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in model output")
    try:
        data = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    return data


def parse_model_json(text: str) -> AIReply:
    data = extract_json(text)
    lead = data.get("lead")
    if lead is not None and (not isinstance(lead, dict) or LeadInfo.model_validate(lead).is_empty()):
        data["lead"] = None
    try:
        return AIReply.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"model JSON failed validation: {exc.errors()[0]['msg']}") from exc


# --------------------------------------------------------------------------- guardrails

_PRICE_RE = re.compile(r"(?:₹|\brs\.?|\binr)\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
_LINK_RE = re.compile(r"(?:https?://|www\.)[^\s<>()\"']+", re.IGNORECASE)
_PHONE_RE = re.compile(r"(?<![\w₹])\+?\d[\d\s-]{8,}\d(?!\w)")
_SENTENCE_END_RE = re.compile(r"[.!?।](?=\s|$)|\n")


def _norm_amount(raw: str) -> str:
    s = raw.replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s.lstrip("0") or "0"


def _phone_keys(text: str) -> set[str]:
    keys = set()
    for m in _PHONE_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) >= 10:
            keys.add(digits[-10:])
    return keys


def check_prices(reply: str, price_sources: str) -> list[str]:
    """Rupee amounts in the reply that do not appear in services/FAQs."""
    known = {_norm_amount(n) for n in _NUMBER_RE.findall(price_sources or "")}
    bad = []
    for m in _PRICE_RE.finditer(reply):
        amount = _norm_amount(m.group(1))
        if amount not in known:
            bad.append(m.group(0).strip())
    return bad


def strip_unknown_links(reply: str, allowed_text: str) -> tuple[str, list[str]]:
    removed: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        link = m.group(0).rstrip(".,;:!?")
        tail = m.group(0)[len(link) :]
        if link.lower() in (allowed_text or "").lower():
            return m.group(0)
        removed.append(link)
        return tail

    return _LINK_RE.sub(_sub, reply), removed


def strip_unknown_phones(reply: str, allowed_text: str) -> tuple[str, list[str]]:
    allowed = _phone_keys(allowed_text)
    removed: list[str] = []

    def _sub(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if len(digits) < 10 or digits[-10:] in allowed:
            return m.group(0)
        removed.append(f"***{digits[-4:]}")
        return ""

    return _PHONE_RE.sub(_sub, reply), removed


def trim_words(text: str, max_words: int) -> tuple[str, bool]:
    """Trim to max_words, preferring to cut at a sentence end."""
    words = list(re.finditer(r"\S+", text))
    if len(words) <= max_words:
        return text, False
    head = text[: words[max_words - 1].end()]
    ends = [m.end() for m in _SENTENCE_END_RE.finditer(head)]
    if ends and ends[-1] >= len(head) * 0.4:
        return head[: ends[-1]].rstrip(), True
    return head.rstrip(" ,;:-") + "…", True


def _tidy(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.!?])", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def apply_guardrails(
    reply: AIReply, kb: Any, max_words: int, extra_allowed_text: str = ""
) -> tuple[AIReply, list[str]]:
    notes: list[str] = []
    out = reply.model_copy(deep=True)
    price_sources = f"{kb.services or ''}\n{kb.faqs or ''}"
    knowledge_text = "\n".join(
        str(getattr(kb, f, "") or "")
        for f in (
            "address",
            "timings",
            "services",
            "faqs",
            "booking_instructions",
            "rules",
            "handoff_contact",
        )
    )

    bad_prices = check_prices(out.reply, price_sources)
    if bad_prices:
        notes.append(f"price_not_in_knowledge: {', '.join(bad_prices)}")
        out.reply = canned("price_confirm", out.language)
        out.handoff = True
        out.handoff_reason = f"Price check: {', '.join(bad_prices)} is not in the approved price list"
        return out, notes

    text, links = strip_unknown_links(out.reply, knowledge_text)
    if links:
        notes.append(f"removed_links: {len(links)}")
    text, phones = strip_unknown_phones(text, f"{knowledge_text}\n{extra_allowed_text}")
    if phones:
        notes.append(f"removed_phone_numbers: {', '.join(phones)}")
    text, trimmed = trim_words(_tidy(text), max_words)
    if trimmed:
        notes.append(f"trimmed_to_{max_words}_words")
    text = _tidy(text)
    if not text:
        notes.append("empty_after_guardrails")
        text = canned("fallback", out.language)
    out.reply = text
    return out, notes


# --------------------------------------------------------------------------- engine


@dataclass
class EngineResult:
    ok: bool
    reply: AIReply | None = None
    model: str | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal = Decimal("0")
    latency_ms: int = 0
    used_fallback: bool = False
    guardrail_notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_messages(client: Any, kb: Any, history: list[dict[str, str]], message: str) -> list[dict[str, str]]:
    msgs = [{"role": "system", "content": build_system_prompt(client, kb)}]
    for h in history:
        role = h.get("role")
        content = (h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": message})
    return msgs


async def generate_reply(
    client: Any,
    kb: Any,
    history: list[dict[str, str]],
    message: str,
    extra_allowed_text: str = "",
) -> EngineResult:
    """Call AI_MODEL; on timeout/HTTP error/bad JSON retry once with AI_FALLBACK_MODEL."""
    s = get_settings()
    messages = build_messages(client, kb, history, message)
    result = EngineResult(ok=False)
    models = [s.AI_MODEL]
    if s.AI_FALLBACK_MODEL and s.AI_FALLBACK_MODEL != s.AI_MODEL:
        models.append(s.AI_FALLBACK_MODEL)

    for i, model in enumerate(models):
        try:
            llm = await chat_completion(model, messages)
        except LLMError as exc:
            log.warning("llm_error", extra={"model": model, "error": str(exc)})
            result.errors.append(str(exc))
            continue
        result.tokens_in += llm.tokens_in
        result.tokens_out += llm.tokens_out
        result.cost_usd += llm.cost_usd
        result.latency_ms += llm.latency_ms
        try:
            parsed = parse_model_json(llm.content)
        except ValueError as exc:
            log.warning("llm_bad_json", extra={"model": model, "error": str(exc)})
            result.errors.append(f"{model}: {exc}")
            continue
        final, notes = apply_guardrails(parsed, kb, s.BOT_REPLY_MAX_WORDS, extra_allowed_text)
        result.ok = True
        result.reply = final
        result.model = llm.model
        result.used_fallback = i > 0
        result.guardrail_notes = notes
        return result
    return result
