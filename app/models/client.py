from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ARRAY, Boolean, Date, DateTime, ForeignKey, Index, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin, str_enum
from app.models.enums import ClientStatus, Niche, Package, Provider


class Client(IdMixin, TimestampMixin, Base):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    niche: Mapped[Niche] = mapped_column(str_enum(Niche, "niche"), nullable=False, default=Niche.other)
    city: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    owner_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    owner_phone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[ClientStatus] = mapped_column(
        str_enum(ClientStatus, "client_status"), nullable=False, default=ClientStatus.lead
    )
    package: Mapped[Package] = mapped_column(
        str_enum(Package, "package"), nullable=False, default=Package.starter
    )
    setup_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    monthly_fee: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    trial_start: Mapped[date | None] = mapped_column(Date)
    live_date: Mapped[date | None] = mapped_column(Date)
    languages: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=lambda: ["English"], server_default=text("'{English}'")
    )
    provider_override: Mapped[Provider | None] = mapped_column(str_enum(Provider, "provider"))
    bot_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_clients_status", "status"),)


class ClientChannel(IdMixin, TimestampMixin, Base):
    __tablename__ = "client_channels"

    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[Provider] = mapped_column(str_enum(Provider, "provider"), nullable=False)
    display_phone: Mapped[str | None] = mapped_column(String(20))
    meta_phone_number_id: Mapped[str | None] = mapped_column(String(64))
    meta_waba_id: Mapped[str | None] = mapped_column(String(64))
    meta_access_token_enc: Mapped[str | None] = mapped_column(Text)
    aisensy_project_id: Mapped[str | None] = mapped_column(String(128))
    aisensy_api_key_enc: Mapped[str | None] = mapped_column(Text)
    aisensy_webhook_secret_enc: Mapped[str | None] = mapped_column(Text)
    channel_token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        Index(
            "uq_client_channels_meta_phone_number_id",
            "meta_phone_number_id",
            unique=True,
            postgresql_where=text("meta_phone_number_id IS NOT NULL"),
        ),
        # One active channel per client.
        Index(
            "uq_client_channels_active_client",
            "client_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )
