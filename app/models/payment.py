from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import PaymentMethod, PaymentType


class Payment(IdMixin, TimestampMixin, Base):
    __tablename__ = "payments"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[PaymentType] = mapped_column(str_enum(PaymentType, "payment_type"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    for_month: Mapped[date | None] = mapped_column(Date)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(str_enum(PaymentMethod, "payment_method"), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_payments_client_for_month", "client_id", "for_month"),)
