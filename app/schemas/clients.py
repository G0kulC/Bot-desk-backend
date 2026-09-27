from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.models import ClientStatus, Niche, Package, Provider
from app.schemas.common import ORMModel
from app.services.phone import normalize_e164


def _phone(v: str | None) -> str | None:
    if v is None or v == "":
        return None
    return normalize_e164(v)


class ClientBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    niche: Niche = Niche.other
    city: str = ""
    owner_name: str = ""
    owner_phone: str | None = Field(None, description="E.164, e.g. +919840012345")
    status: ClientStatus = ClientStatus.lead
    package: Package = Package.starter
    trial_start: date | None = None
    live_date: date | None = None
    languages: list[str] = Field(default_factory=lambda: ["English"])
    provider_override: Provider | None = None
    bot_enabled: bool = True
    notes: str | None = None

    _norm_phone = field_validator("owner_phone")(_phone)


class ClientCreate(ClientBase):
    setup_fee: Decimal | None = Field(None, ge=0, description="Defaults from the package when omitted")
    monthly_fee: Decimal | None = Field(None, ge=0, description="Defaults from the package when omitted")


class ClientUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    niche: Niche | None = None
    city: str | None = None
    owner_name: str | None = None
    owner_phone: str | None = None
    status: ClientStatus | None = None
    package: Package | None = None
    setup_fee: Decimal | None = Field(None, ge=0)
    monthly_fee: Decimal | None = Field(None, ge=0)
    trial_start: date | None = None
    live_date: date | None = None
    languages: list[str] | None = None
    provider_override: Provider | None = None
    bot_enabled: bool | None = None
    notes: str | None = None

    _norm_phone = field_validator("owner_phone")(_phone)


class ClientOut(ORMModel):
    id: uuid.UUID
    name: str
    niche: Niche
    city: str
    owner_name: str
    owner_phone: str | None
    status: ClientStatus
    package: Package
    setup_fee: Decimal
    monthly_fee: Decimal
    trial_start: date | None
    live_date: date | None
    languages: list[str]
    provider_override: Provider | None
    bot_enabled: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime
    effective_provider: Provider
    billing_status: str | None = None
    next_due_date: date | None = None
    setup_paid: bool | None = None
