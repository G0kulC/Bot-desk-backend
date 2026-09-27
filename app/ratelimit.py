from __future__ import annotations

import time

from fastapi import Request

from app.config import get_settings
from app.errors import AppError


class TokenBucketLimiter:
    """Simple in-memory per-key token bucket (single process; fine for v1)."""

    def __init__(self, rate_per_sec: float, burst: int, max_keys: int = 10_000):
        self.rate = rate_per_sec
        self.burst = burst
        self.max_keys = max_keys
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        tokens, last = self._buckets.get(key, (float(self.burst), now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        allowed = tokens >= 1
        if allowed:
            tokens -= 1
        if len(self._buckets) >= self.max_keys and key not in self._buckets:
            self._buckets.clear()
        self._buckets[key] = (tokens, now)
        return allowed


_webhook_limiter: TokenBucketLimiter | None = None


def webhook_limiter() -> TokenBucketLimiter:
    global _webhook_limiter
    if _webhook_limiter is None:
        s = get_settings()
        _webhook_limiter = TokenBucketLimiter(s.WEBHOOK_RATE_PER_SEC, s.WEBHOOK_RATE_BURST)
    return _webhook_limiter


async def webhook_rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    if not webhook_limiter().allow(ip):
        raise AppError(429, "rate_limited", "Too many webhook requests")
