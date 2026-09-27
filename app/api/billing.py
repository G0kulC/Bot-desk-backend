from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models import Client, ClientStatus
from app.schemas.payments import RenewalOut
from app.services.billing import billing_for_clients
from app.timeutil import today_ist

router = APIRouter(prefix="/billing", tags=["billing"])


@router.get("/renewals", response_model=list[RenewalOut])
async def renewals(session: SessionDep, _: CurrentUser) -> list[RenewalOut]:
    clients = list(
        await session.scalars(
            select(Client)
            .where(Client.deleted_at.is_(None), Client.status == ClientStatus.live)
            .order_by(Client.name)
        )
    )
    info = await billing_for_clients(session, clients, today_ist())
    out = [
        RenewalOut(
            client_id=c.id,
            client_name=c.name,
            package=c.package.value,
            setup_fee=c.setup_fee,
            amount=c.monthly_fee,
            due_date=info[c.id].due_date,
            status=info[c.id].status,
            setup_paid=info[c.id].setup_paid,
            period_month=info[c.id].period_month,
        )
        for c in clients
    ]
    order = {"overdue": 0, "due": 1, "upcoming": 2, "paid": 3}
    out.sort(key=lambda r: (order.get(r.status, 9), r.due_date or r.period_month or today_ist()))
    return out
