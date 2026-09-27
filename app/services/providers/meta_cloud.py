"""`own` provider: Meta WhatsApp Cloud API directly."""

from __future__ import annotations

import hashlib
import hmac
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx

from app.config import get_settings
from app.security import decrypt_secret
from app.services.providers.base import InboundEvent, InboundKind, SendResult, lower_headers

if TYPE_CHECKING:
    from app.models import ClientChannel

log = logging.getLogger(__name__)

SIGNATURE_HEADER = "x-hub-signature-256"
_TEXTLIKE = {"text", "button", "interactive"}
_TYPE_MAP = {"image": "image", "sticker": "image", "audio": "audio", "voice": "audio", "location": "location"}


def _ts(value: str | int | None) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), UTC) if value else None
    except (TypeError, ValueError):
        return None


class MetaCloudProvider:
    name = "own"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    # ------------------------------------------------------------------ sending

    def _url(self, channel: ClientChannel) -> str:
        s = get_settings()
        return (
            f"{s.META_GRAPH_BASE.rstrip('/')}/{s.META_GRAPH_VERSION}/{channel.meta_phone_number_id}/messages"
        )

    async def _post(self, channel: ClientChannel, body: dict) -> SendResult:
        token = decrypt_secret(channel.meta_access_token_enc)
        if not channel.meta_phone_number_id or not token:
            return SendResult(ok=False, error="Channel is missing the Meta phone number id or access token")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as http:
                resp = await http.post(
                    self._url(channel), json=body, headers={"Authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as exc:
            return SendResult(ok=False, error=f"Meta request failed: {exc.__class__.__name__}")
        try:
            data = resp.json()
        except ValueError:
            data = {"text": resp.text[:500]}
        if resp.status_code >= 400:
            err = data.get("error", {}) if isinstance(data, dict) else {}
            msg = err.get("message") or f"HTTP {resp.status_code}"
            code = err.get("code")
            return SendResult(
                ok=False,
                status_code=resp.status_code,
                error=f"{msg} (code {code})" if code else msg,
                raw=data,
            )
        msg_id = None
        if isinstance(data, dict) and data.get("messages"):
            msg_id = data["messages"][0].get("id")
        return SendResult(ok=True, provider_message_id=msg_id, status_code=resp.status_code, raw=data)

    async def send_text(self, channel: ClientChannel, to_wa_id: str, body: str) -> SendResult:
        return await self._post(
            channel,
            {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to_wa_id,
                "type": "text",
                "text": {"preview_url": False, "body": body},
            },
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
                "messaging_product": "whatsapp",
                "to": to_wa_id,
                "type": "template",
                "template": {"name": template, "language": {"code": lang}, "components": components},
            },
        )

    async def mark_read(self, channel: ClientChannel, provider_message_id: str) -> None:
        result = await self._post(
            channel, {"messaging_product": "whatsapp", "status": "read", "message_id": provider_message_id}
        )
        if not result.ok:
            log.info("meta_mark_read_failed", extra={"error": result.error})

    # ------------------------------------------------------------------ receiving

    def verify_signature(
        self, raw_body: bytes, headers: Mapping[str, str], channel: ClientChannel | None = None
    ) -> bool:
        secret = get_settings().META_APP_SECRET
        header = lower_headers(headers).get(SIGNATURE_HEADER, "")
        if not secret or not header.startswith("sha256="):
            return False
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, header.removeprefix("sha256="))

    def parse_inbound(self, payload: dict) -> list[InboundEvent]:
        events: list[InboundEvent] = []
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
                names = {
                    c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts") or []
                }
                for m in value.get("messages") or []:
                    events.append(self._parse_message(m, names, phone_number_id))
                for st in value.get("statuses") or []:
                    errors = st.get("errors") or []
                    err = None
                    if errors:
                        e = errors[0]
                        err = e.get("message") or e.get("title") or str(e.get("code"))
                        details = (e.get("error_data") or {}).get("details")
                        if details:
                            err = f"{err}: {details}"
                    events.append(
                        InboundEvent(
                            kind=InboundKind.status,
                            provider=self.name,
                            wa_id=st.get("recipient_id") or "",
                            provider_message_id=st.get("id"),
                            status=st.get("status"),
                            error=err,
                            timestamp=_ts(st.get("timestamp")),
                            channel_ref=phone_number_id,
                            raw=st,
                        )
                    )
        return events

    def _parse_message(self, m: dict, names: dict, phone_number_id: str | None) -> InboundEvent:
        mtype = m.get("type") or "unknown"
        body: str | None = None
        msg_type = "other"
        if mtype == "text":
            body, msg_type = (m.get("text") or {}).get("body"), "text"
        elif mtype == "button":
            body, msg_type = (m.get("button") or {}).get("text"), "text"
        elif mtype == "interactive":
            inter = m.get("interactive") or {}
            reply = inter.get("button_reply") or inter.get("list_reply") or {}
            body, msg_type = reply.get("title"), "text"
        elif mtype == "location":
            loc = m.get("location") or {}
            parts = [loc.get("name"), loc.get("address"), f"{loc.get('latitude')},{loc.get('longitude')}"]
            body, msg_type = " | ".join(str(p) for p in parts if p), "location"
        elif mtype in _TYPE_MAP:
            media = m.get(mtype) or {}
            body = media.get("caption") or f"[{mtype}]"
            msg_type = _TYPE_MAP[mtype]
        else:
            body = f"[{mtype}]"
        wa_id = m.get("from") or ""
        return InboundEvent(
            kind=InboundKind.message,
            provider=self.name,
            wa_id=wa_id,
            provider_message_id=m.get("id"),
            msg_type=msg_type if (body or mtype not in _TEXTLIKE) else "other",
            body=body,
            profile_name=names.get(wa_id),
            timestamp=_ts(m.get("timestamp")),
            channel_ref=phone_number_id,
            raw=m,
        )
