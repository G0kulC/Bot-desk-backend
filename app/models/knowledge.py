from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin

# Fields that make up the knowledge content (copied into every version snapshot).
KNOWLEDGE_FIELDS = (
    "address",
    "timings",
    "services",
    "faqs",
    "booking_instructions",
    "rules",
    "handoff_contact",
    "tone",
)
# Changing any of these resets approval.
APPROVAL_SENSITIVE_FIELDS = ("services", "faqs", "rules")


class KnowledgeBase(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_bases"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    address: Mapped[str] = mapped_column(Text, nullable=False, default="")
    timings: Mapped[str] = mapped_column(Text, nullable=False, default="")
    services: Mapped[str] = mapped_column(Text, nullable=False, default="")
    faqs: Mapped[str] = mapped_column(Text, nullable=False, default="")
    booking_instructions: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rules: Mapped[str] = mapped_column(Text, nullable=False, default="")
    handoff_contact: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tone: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_name: Mapped[str | None] = mapped_column(String(255))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    def snapshot(self) -> dict[str, str]:
        return {f: getattr(self, f) or "" for f in KNOWLEDGE_FIELDS}


class KnowledgeVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_versions"

    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    saved_by: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "version", name="uq_knowledge_versions_kb_version"),
    )
