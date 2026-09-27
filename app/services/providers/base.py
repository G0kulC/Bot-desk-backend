from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from app.models import ClientChannel


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str | None = None
    status_code: int | None = None
    error: str | None = None
    raw: dict | None = None


class InboundKind(StrEnum):
    message = "message"  # customer -> business (text or non-text)
    status = "status"  # delivery / read / failed update for a message we sent
    agent_message = "agent_message"  # human agent replied from the provider's inbox (AiSensy)


@dataclass
class InboundEvent:
    kind: InboundKind
    provider: str
    wa_id: str
    provider_message_id: str | None = None
    msg_type: str = "text"  # text | image | audio | location | other
    body: str | None = None
    profile_name: str | None = None
    timestamp: datetime | None = None
    status: str | None = None  # sent | delivered | read | failed (status events)
    error: str | None = None
    channel_ref: str | None = None  # Meta phone_number_id, used for routing
    raw: dict = field(default_factory=dict)


@runtime_checkable
class WhatsAppProvider(Protocol):
    name: str

    async def send_text(self, channel: ClientChannel, to_wa_id: str, body: str) -> SendResult: ...

    async def send_template(
        self, channel: ClientChannel, to_wa_id: str, template: str, lang: str, params: list[str]
    ) -> SendResult: ...

    async def mark_read(self, channel: ClientChannel, provider_message_id: str) -> None: ...

    def parse_inbound(self, payload: dict) -> list[InboundEvent]: ...

    def verify_signature(
        self, raw_body: bytes, headers: Mapping[str, str], channel: ClientChannel | None
    ) -> bool: ...


def lower_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {k.lower(): v for k, v in headers.items()}
