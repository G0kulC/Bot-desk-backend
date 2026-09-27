"""`aisensy` provider: AiSensy Project API as the WhatsApp transport; replies still come from our AI.

Docs: https://aisensy.stoplight.io/docs/project-api/effdec8a4894f-send-message
      https://aisensy.stoplight.io/docs/project-api/56ea5a8f1cc9a-project-webhook

Everything AiSensy-specific (paths, header names, webhook topics and field names) lives in the
constants block below. See README "AiSensy: verified vs assumed" before going live.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from app.config import get_settings
from app.security import decrypt_secret
from app.services.providers.base import InboundEvent, InboundKind, SendResult, lower_headers
from app.services.providers.meta_cloud import MetaCloudProvider

if TYPE_CHECKING:
    from app.models import ClientChannel

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------
# AiSensy constants (single place to adjust if AiSensy's API differs from these)
# ---------------------------------------------------------------------------------------------
SEND_PATH = "/project/{project_id}/messages"  # POST, Meta-like body, Meta-like response
AUTH_HEADER = "X-AiSensy-Project-API-Pwd"  # Project API password
SIGNATURE_HEADER = "X-AiSensy-Signature"  # HMAC-SHA256 of the raw body with the webhook secret
# Mark-as-read is not part of the documented Project API send endpoint; AiSensy's inbox manages
# read receipts, so mark_read is a deliberate no-op unless a path is configured here.
MARK_READ_PATH: str | None = None

# Webhook topics
TOPIC_INBOUND = {"message.sender.user", "message.received", "message.inbound"}
TOPIC_STATUS = {"message.status.updated", "message.status", "message.updated"}
# Values of `sender` meaning "a human replied from the AiSensy inbox" (takeover).
AGENT_SENDERS = {"AGENT", "USER_AGENT", "TEAM_MEMBER", "HUMAN", "OPERATOR", "BUSINESS_AGENT"}
CUSTOMER_SENDERS = {"USER", "CUSTOMER", "CONTACT"}
# Messages we sent via the API (echoes) or campaigns: ignored.
IGNORED_SENDERS = {"API", "BOT", "SYSTEM", "CAMPAIGN", "BROADCAST", "CHATBOT"}

_TYPE_MAP = {
    "text": "text",
    "button": "text",
    "interactive": "text",
    "image": "image",
    "sticker": "image",
    "audio": "audio",
    "voice": "audio",
    "location": "location",
}


def _first(d: Mapping[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", {}):
            return v
    return None


def _to_dt(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        num = float(value)
        return datetime.fromtimestamp(num / 1000 if num > 1e11 else num, UTC)
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    except ValueError:
        return None


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


class AiSensyProvider:
    name = "aisensy"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    # ------------------------------------------------------------------ sending

    def _url(self, channel: ClientChannel, path: str) -> str:
        base = get_settings().AISENSY_API_BASE.rstrip("/")
        return base + path.format(project_id=channel.aisensy_project_id)

    async def _post(self, channel: ClientChannel, body: dict) -> SendResult:
        password = decrypt_secret(channel.aisensy_api_key_enc)
        if not channel.aisensy_project_id or not password:
            return SendResult(ok=False, error="Channel is missing the AiSensy project id or API password")
        headers = {AUTH_HEADER: password, "Accept": "application/json", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(self._url(channel, SEND_PATH), json=body, headers=headers)
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"AiSensy request failed: {exc.__class__.__name__}")
        try:
            data = resp.json()
        except ValueError:
            data = {"text": resp.text[:500]}
        if resp.status_code >= 400:
            err = data.get("error") if isinstance(data, dict) else None
            msg = (err.get("message") if isinstance(err, dict) else err) or (
                data.get("message") if isinstance(data, dict) else None
            )
            return SendResult(
                ok=False, status_code=resp.status_code, error=msg or f"HTTP {resp.status_code}", raw=data
            )
        msg_id = None
        if isinstance(data, dict):
            msgs = data.get("messages") or []
            msg_id = (msgs[0].get("id") if msgs else None) or data.get("id") or data.get("messageId")
        return SendResult(ok=True, provider_message_id=msg_id, status_code=resp.status_code, raw=data)

    async def send_text(self, channel: ClientChannel, to_wa_id: str, body: str) -> SendResult:
        return await self._post(
            channel,
            {"to": to_wa_id, "type": "text", "recipient_type": "individual", "text": {"body": body}},
        )

    async def send_template(
        self, channel: ClientChannel, to_wa_id: str, template: str, lang: str, params: list[str]
    ) -> SendResult:
        components = []
        if params:
            components.append(
                {"type": "body", "parameters": [{"type": "text", "text": p or "-"} for p in params]}
            )
        return await self._post(
            channel,
            {
                "to": to_wa_id,
                "type": "template",
                "template": {"name": template, "language": {"policy": "deterministic", "code": lang},
                             "components": components},
            },
        )  # fmt: skip

    async def mark_read(self, channel: ClientChannel, provider_message_id: str) -> None:
        if MARK_READ_PATH is None:
            return
        await self._post(channel, {"status": "read", "message_id": provider_message_id})

    # ------------------------------------------------------------------ receiving

    def verify_signature(
        self, raw_body: bytes, headers: Mapping[str, str], channel: ClientChannel | None
    ) -> bool:
        """The per-channel URL token is the first check (done by the route). If a webhook secret is
        configured for the channel, the HMAC signature must also match (hex, 'sha256=' hex, or base64)."""
        secret = decrypt_secret(channel.aisensy_webhook_secret_enc) if channel else None
        if not secret:
            return True
        header = lower_headers(headers).get(SIGNATURE_HEADER.lower(), "").strip()
        if not header:
            return False
        digest = hmac.new(secret.encode(), raw_body, hashlib.sha256).digest()
        candidates = {digest.hex(), base64.b64encode(digest).decode()}
        given = header.removeprefix("sha256=")
        return any(hmac.compare_digest(given, c) for c in candidates)

    def parse_inbound(self, payload: dict) -> list[InboundEvent]:
        # Some AiSensy setups forward Meta's raw format; reuse the Meta parser for those.
        if isinstance(payload.get("entry"), list):
            events = MetaCloudProvider().parse_inbound(payload)
            for e in events:
                e.provider = self.name
                e.channel_ref = None  # AiSensy channels are routed by the URL token
            return events

        topic = str(payload.get("topic") or payload.get("event") or "").lower()
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        items = data.get("messages") if isinstance(data.get("messages"), list) else None
        if items is None:
            msg = data.get("message") if isinstance(data.get("message"), dict) else data
            items = [msg]
        contact = data.get("contact") if isinstance(data.get("contact"), dict) else {}
        events = []
        for m in items:
            ev = self._parse_item(m, topic, contact, payload)
            if ev is not None:
                events.append(ev)
        return events

    def _parse_item(self, m: dict, topic: str, contact: dict, payload: dict) -> InboundEvent | None:
        msg_id = _first(m, "id", "messageId", "message_id", "wamid", "whatsapp_message_id")
        phone = _digits(
            _first(
                m, "phone_number", "phoneNumber", "from", "wa_id", "waId", "userNumber", "to", "destination"
            )
            or _first(contact, "phone_number", "phoneNumber", "wa_id")
        )
        status = str(_first(m, "status", "message_status") or "").lower() or None
        ts = _to_dt(_first(m, "timestamp", "created_at", "createdAt", "sent_at") or payload.get("created_at"))

        if topic in TOPIC_STATUS or (status and not topic and not _first(m, "message_content", "text")):
            if not msg_id or not status:
                return None
            err = _first(m, "error", "failure_reason", "failedReason")
            if isinstance(err, dict):
                err = err.get("message") or err.get("title")
            return InboundEvent(
                kind=InboundKind.status,
                provider=self.name,
                wa_id=phone,
                provider_message_id=str(msg_id),
                status=status,
                error=str(err) if err else None,
                timestamp=ts,
                raw=m,
            )

        sender = str(_first(m, "sender", "sent_by", "sentBy", "sender_type", "direction") or "").upper()
        if topic in TOPIC_INBOUND or sender in CUSTOMER_SENDERS or sender == "INBOUND":
            kind = InboundKind.message
        elif sender in AGENT_SENDERS:
            kind = InboundKind.agent_message
        else:
            if sender and sender not in IGNORED_SENDERS:
                log.info("aisensy_unknown_sender", extra={"sender": sender, "topic": topic})
            return None

        raw_type = str(_first(m, "message_type", "messageType", "type") or "text").lower()
        msg_type = _TYPE_MAP.get(raw_type, "other")
        content = _first(m, "message_content", "content", raw_type) or {}
        body: str | None = None
        if isinstance(content, str):
            body = content
        elif isinstance(content, dict):
            body = _first(content, "text", "body", "caption", "title")
            if isinstance(body, dict):
                body = body.get("body")
            if raw_type == "location":
                parts = [content.get("name"), content.get("address"),
                         f"{content.get('latitude')},{content.get('longitude')}"]  # fmt: skip
                body = " | ".join(str(p) for p in parts if p)
        if body is None and isinstance(m.get("text"), str):
            body = m["text"]
        if body is None and msg_type != "text":
            body = f"[{raw_type}]"
        name = _first(m, "userName", "user_name", "name", "profile_name") or _first(
            contact, "name", "userName"
        )
        return InboundEvent(
            kind=kind,
            provider=self.name,
            wa_id=phone,
            provider_message_id=str(msg_id) if msg_id else None,
            msg_type=msg_type if body else "other",
            body=body,
            profile_name=str(name) if name else None,
            timestamp=ts,
            raw=m,
        )
