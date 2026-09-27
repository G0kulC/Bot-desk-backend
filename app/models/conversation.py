from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import Direction, LeadStatus, MsgStatus, MsgType, Provider, Sender


class Contact(IdMixin, TimestampMixin, Base):
    __tablename__ = "contacts"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    wa_id: Mapped[str] = mapped_column(String(32), nullable=False)
    profile_name: Mapped[str | None] = mapped_column(String(255))
    detected_language: Mapped[str | None] = mapped_column(String(32))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handoff_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    handoff_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    handoff_reason: Mapped[str | None] = mapped_column(Text)
    opted_out: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (UniqueConstraint("client_id", "wa_id", name="uq_contacts_client_wa"),)


class Message(IdMixin, TimestampMixin, Base):
    __tablename__ = "messages"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[Direction] = mapped_column(str_enum(Direction, "direction"), nullable=False)
    sender: Mapped[Sender] = mapped_column(str_enum(Sender, "sender"), nullable=False)
    provider: Mapped[Provider | None] = mapped_column(str_enum(Provider, "provider"))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    msg_type: Mapped[MsgType] = mapped_column(
        str_enum(MsgType, "msg_type"), nullable=False, default=MsgType.text
    )
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MsgStatus] = mapped_column(str_enum(MsgStatus, "msg_status"), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    ai_model: Mapped[str | None] = mapped_column(String(128))
    tokens_in: Mapped[int | None] = mapped_column(Integer)
    tokens_out: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    # Extra context: skip reason, guardrail notes, detected language, owner-alert info.
    meta: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (
        Index(
            "uq_messages_provider_message_id",
            "provider_message_id",
            unique=True,
            postgresql_where=text("provider_message_id IS NOT NULL"),
        ),
        Index("ix_messages_client_created", "client_id", "created_at"),
        Index("ix_messages_contact_created", "contact_id", "created_at"),
    )


class Lead(IdMixin, TimestampMixin, Base):
    __tablename__ = "leads"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    phone: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    need: Mapped[str] = mapped_column(Text, nullable=False, default="")
    preferred_time: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[LeadStatus] = mapped_column(
        str_enum(LeadStatus, "lead_status"), nullable=False, default=LeadStatus.new
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
