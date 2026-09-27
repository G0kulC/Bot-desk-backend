from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from app.models import Direction, LeadStatus, MsgStatus, MsgType, Sender
from app.schemas.common import ORMModel


class InboxItem(BaseModel):
    contact_id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    wa_id: str
    profile_name: str | None
    detected_language: str | None
    handoff_active: bool
    handoff_reason: str | None
    opted_out: bool
    last_inbound_at: datetime | None
    can_reply: bool = Field(description="True if the customer wrote within the last 24 hours")
    unread_count: int
    last_message_at: datetime
    last_message_preview: str | None
    last_message_sender: Sender


class MessageOut(ORMModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    direction: Direction
    sender: Sender
    msg_type: MsgType
    body: str | None
    status: MsgStatus
    error: str | None
    ai_model: str | None
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: Decimal | None
    latency_ms: int | None
    meta: dict | None
    created_at: datetime


class ContactOut(ORMModel):
    id: uuid.UUID
    client_id: uuid.UUID
    wa_id: str
    profile_name: str | None
    detected_language: str | None
    first_seen_at: datetime
    last_inbound_at: datetime | None
    handoff_active: bool
    handoff_since: datetime | None
    handoff_reason: str | None
    opted_out: bool


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=4096)


class HandoffIn(BaseModel):
    active: bool
    reason: str | None = None


class OptOutIn(BaseModel):
    opted_out: bool


class LeadCreate(BaseModel):
    client_id: uuid.UUID
    contact_id: uuid.UUID | None = None
    name: str = ""
    phone: str = ""
    need: str = ""
    preferred_time: str = ""
    status: LeadStatus = LeadStatus.new
    notes: str | None = None


class LeadUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    need: str | None = None
    preferred_time: str | None = None
    status: LeadStatus | None = None
    notes: str | None = None


class LeadOut(ORMModel):
    id: uuid.UUID
    client_id: uuid.UUID
    contact_id: uuid.UUID | None
    name: str
    phone: str
    need: str
    preferred_time: str
    status: LeadStatus
    source_message_id: uuid.UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
