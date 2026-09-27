from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.models import PaymentMethod, PaymentType
from app.schemas.common import ORMModel


class PaymentCreate(BaseModel):
    client_id: uuid.UUID
    type: PaymentType
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    for_month: date | None = Field(None, description="Monthly payments only; normalised to the 1st")
    paid_on: date | None = Field(None, description="Defaults to today (IST)")
    method: PaymentMethod = PaymentMethod.upi
    reference: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check_month(self) -> PaymentCreate:
        if self.type == PaymentType.monthly:
            if self.for_month is None:
                raise ValueError("for_month is required for monthly payments")
            self.for_month = self.for_month.replace(day=1)
        else:
            self.for_month = None
        return self


class PaymentOut(ORMModel):
    id: uuid.UUID
    client_id: uuid.UUID
    type: PaymentType
    amount: Decimal
    for_month: date | None
    paid_on: date
    method: PaymentMethod
    reference: str | None
    note: str | None
    created_at: datetime


class RenewalOut(BaseModel):
    client_id: uuid.UUID
    client_name: str
    package: str
    setup_fee: Decimal
    amount: Decimal
    due_date: date | None
    status: str
    setup_paid: bool
    period_month: date | None = None
