from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.config import get_settings


class LLMError(Exception):
    """Timeout, HTTP error or empty response from the model provider."""


@dataclass
class LLMResult:
    content: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: Decimal
    latency_ms: int


async def chat_completion(model: str, messages: list[dict[str, str]]) -> LLMResult:
    s = get_settings()
    url = f"{s.OPENROUTER_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {s.OPENROUTER_API_KEY}",
        "HTTP-Referer": s.APP_BASE_URL,
        "X-Title": "Bot Desk",
    }
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": s.AI_MAX_OUTPUT_TOKENS,
        "temperature": s.AI_TEMPERATURE,
        # Ask OpenRouter to include the real cost (USD) in `usage.cost`.
        "usage": {"include": True},
    }
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=s.AI_TIMEOUT_SECONDS) as http:
            resp = await http.post(url, json=body, headers=headers)
    except httpx.TimeoutException as exc:
        raise LLMError(f"{model}: timeout after {s.AI_TIMEOUT_SECONDS}s") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"{model}: {exc.__class__.__name__}") from exc
    latency_ms = int((time.perf_counter() - started) * 1000)
    if resp.status_code >= 400:
        raise LLMError(f"{model}: HTTP {resp.status_code} {resp.text[:200]}")
    try:
        data = resp.json()
        if "error" in data and not data.get("choices"):
            raise LLMError(f"{model}: {str(data['error'])[:200]}")
        content = data["choices"][0]["message"]["content"] or ""
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise LLMError(f"{model}: malformed response") from exc
    if not content.strip():
        raise LLMError(f"{model}: empty content")
    usage = data.get("usage") or {}
    return LLMResult(
        content=content,
        model=data.get("model") or model,
        tokens_in=int(usage.get("prompt_tokens") or 0),
        tokens_out=int(usage.get("completion_tokens") or 0),
        cost_usd=Decimal(str(usage.get("cost") or 0)),
        latency_ms=latency_ms,
    )
