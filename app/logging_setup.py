from __future__ import annotations

import json
import logging
import re
import uuid
from contextvars import ContextVar
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Any run of 10+ digits (optionally with +, spaces or dashes) is treated as a phone number in logs.
_PHONE_RE = re.compile(r"\+?\d[\d\s-]{8,}\d")


def mask_phones_in_text(text: str) -> str:
    def _mask(m: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        return f"***{digits[-4:]}" if len(digits) >= 10 else m.group(0)

    return _PHONE_RE.sub(_mask, text)


class JsonFormatter(logging.Formatter):
    _SKIP = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": mask_phones_in_text(record.getMessage()),
            "request_id": request_id_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in self._SKIP and not key.startswith("_"):
                payload[key] = mask_phones_in_text(str(value)) if isinstance(value, str) else value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # httpx logs full URLs at INFO; keep them quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response
