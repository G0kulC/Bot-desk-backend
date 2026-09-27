"""Renewal / due-date logic.

Rules:
* The first monthly fee is due on `live_date`, then on the same day every month. If a month is
  shorter, the last day of that month is used (31 Jan -> 28/29 Feb, back to 31 Mar).
* P = the latest due date <= today (IST). N = the due date after P.
* P unpaid (no monthly payment whose for_month is P's month): `due` if today is 0-3 days after P,
  otherwise `overdue`. due_date = P.
* P paid: `due` if N is within 5 days, otherwise `paid`. due_date = N.
* live_date in the future (or not set): `upcoming`.
* setup_paid = any payment of type `setup`.
"""

from __future__ import annotations

import calendar
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, ClientStatus, Payment, PaymentType

DUE_GRACE_DAYS = 3
DUE_SOON_DAYS = 5


class BillingStatus:
    upcoming = "upcoming"
    due = "due"
    overdue = "overdue"
    paid = "paid"
    not_live = "not_live"


@dataclass(frozen=True)
class BillingInfo:
    status: str
    due_date: date | None
    period_month: date | None  # first-of-month of the period the status refers to
    setup_paid: bool
    amount: Decimal = Decimal("0")


def add_months(anchor: date, months: int) -> date:
    """anchor + n months, clamping the day to the target month's last day."""
    total = anchor.month - 1 + months
    year, month = anchor.year + total // 12, total % 12 + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def current_period_index(live_date: date, today: date) -> int:
    """Index k of the latest due date <= today (due date k = add_months(live_date, k))."""
    k = (today.year - live_date.year) * 12 + (today.month - live_date.month)
    if add_months(live_date, k) > today:
        k -= 1
    return k


def compute_billing(
    live_date: date | None,
    today: date,
    paid_months: Iterable[date],
    setup_paid: bool = False,
    amount: Decimal = Decimal("0"),
) -> BillingInfo:
    if live_date is None or live_date > today:
        return BillingInfo(BillingStatus.upcoming, live_date, live_date.replace(day=1) if live_date else None,
                           setup_paid, amount)  # fmt: skip
    paid = {d.replace(day=1) for d in paid_months}
    k = current_period_index(live_date, today)
    p = add_months(live_date, k)
    n = add_months(live_date, k + 1)
    if p.replace(day=1) not in paid:
        days_late = (today - p).days
        status = BillingStatus.due if 0 <= days_late <= DUE_GRACE_DAYS else BillingStatus.overdue
        return BillingInfo(status, p, p.replace(day=1), setup_paid, amount)
    status = BillingStatus.due if (n - today).days <= DUE_SOON_DAYS else BillingStatus.paid
    return BillingInfo(status, n, n.replace(day=1), setup_paid, amount)


async def billing_for_clients(
    session: AsyncSession, clients: list[Client], today: date
) -> dict[uuid.UUID, BillingInfo]:
    """Billing info for many clients with one payments query. Non-live clients get `not_live`."""
    ids = [c.id for c in clients]
    if not ids:
        return {}
    rows = (
        await session.execute(
            select(Payment.client_id, Payment.type, Payment.for_month).where(Payment.client_id.in_(ids))
        )
    ).all()
    months: dict[uuid.UUID, set[date]] = {i: set() for i in ids}
    setup: dict[uuid.UUID, bool] = dict.fromkeys(ids, False)
    for client_id, ptype, for_month in rows:
        if ptype == PaymentType.setup:
            setup[client_id] = True
        elif ptype == PaymentType.monthly and for_month:
            months[client_id].add(for_month)
    out: dict[uuid.UUID, BillingInfo] = {}
    for c in clients:
        if c.status != ClientStatus.live:
            out[c.id] = BillingInfo(BillingStatus.not_live, None, None, setup[c.id], c.monthly_fee)
        else:
            out[c.id] = compute_billing(c.live_date, today, months[c.id], setup[c.id], c.monthly_fee)
    return out
