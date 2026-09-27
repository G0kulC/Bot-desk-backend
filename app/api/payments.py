from __future__ import annotations

import re
import uuid
from datetime import date

from fastapi import APIRouter, Query, status
from sqlalchemy import and_, extract, or_, select

from app.api.deps import CurrentUser, SessionDep
from app.errors import AppError, not_found
from app.models import Payment, PaymentType
from app.schemas.common import OkOut
from app.schemas.payments import PaymentCreate, PaymentOut
from app.services.audit import audit
from app.services.clients import get_client_or_404
from app.timeutil import today_ist

router = APIRouter(prefix="/payments", tags=["payments"])

_MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def parse_month(value: str) -> tuple[int, int]:
    m = _MONTH_RE.match(value)
    if not m:
        raise AppError(422, "validation_error", "month must be YYYY-MM")
    return int(m.group(1)), int(m.group(2))


@router.get("", response_model=list[PaymentOut])
async def list_payments(
    session: SessionDep,
    _: CurrentUser,
    client_id: uuid.UUID | None = None,
    type: PaymentType | None = None,
    month: str | None = Query(None, description="YYYY-MM: matches for_month, or paid_on for non-monthly"),
) -> list[Payment]:
    stmt = select(Payment)
    if client_id:
        stmt = stmt.where(Payment.client_id == client_id)
    if type:
        stmt = stmt.where(Payment.type == type)
    if month:
        y, m = parse_month(month)
        stmt = stmt.where(
            or_(
                Payment.for_month == date(y, m, 1),
                and_(
                    Payment.for_month.is_(None),
                    extract("year", Payment.paid_on) == y,
                    extract("month", Payment.paid_on) == m,
                ),
            )
        )
    rows = await session.scalars(stmt.order_by(Payment.paid_on.desc(), Payment.created_at.desc()))
    return list(rows)


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(body: PaymentCreate, session: SessionDep, user: CurrentUser) -> Payment:
    await get_client_or_404(session, body.client_id)
    data = body.model_dump()
    data["paid_on"] = data["paid_on"] or today_ist()
    payment = Payment(**data)
    session.add(payment)
    await session.flush()
    audit(session, user, "payment.create", "payment", payment.id, data)
    await session.commit()
    await session.refresh(payment)
    return payment


@router.delete("/{payment_id}", response_model=OkOut)
async def delete_payment(payment_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> OkOut:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise not_found("Payment")
    snapshot = {
        "client_id": payment.client_id,
        "type": payment.type,
        "amount": payment.amount,
        "for_month": payment.for_month,
        "paid_on": payment.paid_on,
    }
    await session.delete(payment)
    audit(session, user, "payment.delete", "payment", payment_id, snapshot)
    await session.commit()
    return OkOut()
