from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status
from sqlalchemy import func, or_, select

from app.api.deps import CurrentUser, SessionDep
from app.models import Client, ClientStatus, Niche, Package
from app.schemas.clients import ClientCreate, ClientOut, ClientUpdate
from app.schemas.common import OkOut, Page
from app.services.audit import audit, changes
from app.services.billing import BillingInfo, billing_for_clients
from app.services.clients import get_client_or_404
from app.services.packages import default_fees
from app.services.providers.factory import effective_provider
from app.timeutil import today_ist, utcnow

router = APIRouter(prefix="/clients", tags=["clients"])


def _client_out(client: Client, billing: BillingInfo | None = None) -> ClientOut:
    data = {c: getattr(client, c) for c in ClientOut.model_fields if hasattr(client, c)}
    data["effective_provider"] = effective_provider(client)
    if billing is not None:
        data["billing_status"] = billing.status
        data["next_due_date"] = billing.due_date
        data["setup_paid"] = billing.setup_paid
    return ClientOut(**data)


async def _outs(session: SessionDep, clients: list[Client]) -> list[ClientOut]:
    info = await billing_for_clients(session, clients, today_ist())
    return [_client_out(c, info.get(c.id)) for c in clients]


@router.get("", response_model=Page[ClientOut])
async def list_clients(
    session: SessionDep,
    _: CurrentUser,
    status_: ClientStatus | None = Query(None, alias="status"),
    niche: Niche | None = None,
    q: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
) -> Page[ClientOut]:
    stmt = select(Client).where(Client.deleted_at.is_(None))
    if status_:
        stmt = stmt.where(Client.status == status_)
    if niche:
        stmt = stmt.where(Client.niche == niche)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Client.name.ilike(like), Client.city.ilike(like), Client.owner_name.ilike(like))
        )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = (
        await session.scalars(
            stmt.order_by(Client.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return Page(items=await _outs(session, list(rows)), total=total, page=page, page_size=page_size)


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(body: ClientCreate, session: SessionDep, user: CurrentUser) -> ClientOut:
    data = body.model_dump()
    fees = default_fees(body.package)
    if data["setup_fee"] is None:
        data["setup_fee"] = fees[0] if fees else 0
    if data["monthly_fee"] is None:
        data["monthly_fee"] = fees[1] if fees else 0
    client = Client(**data)
    session.add(client)
    await session.flush()
    audit(session, user, "client.create", "client", client.id, data)
    await session.commit()
    await session.refresh(client)
    return (await _outs(session, [client]))[0]


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> ClientOut:
    return (await _outs(session, [await get_client_or_404(session, client_id)]))[0]


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(
    client_id: uuid.UUID, body: ClientUpdate, session: SessionDep, user: CurrentUser
) -> ClientOut:
    client = await get_client_or_404(session, client_id)
    data = body.model_dump(exclude_unset=True)
    new_package = data.get("package")
    if new_package and new_package != client.package and new_package != Package.custom:
        fees = default_fees(new_package)
        if fees:
            data.setdefault("setup_fee", fees[0])
            data.setdefault("monthly_fee", fees[1])
    for key in ("name", "niche", "status", "package", "languages", "bot_enabled", "city", "owner_name"):
        if key in data and data[key] is None:
            data.pop(key)
    diff = changes(client, data)
    for key, value in data.items():
        setattr(client, key, value)
    if diff:
        audit(session, user, "client.update", "client", client.id, diff)
    await session.commit()
    await session.refresh(client)
    return (await _outs(session, [client]))[0]


@router.delete("/{client_id}", response_model=OkOut)
async def delete_client(client_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> OkOut:
    client = await get_client_or_404(session, client_id)
    client.deleted_at = utcnow()
    client.bot_enabled = False
    audit(session, user, "client.delete", "client", client.id)
    await session.commit()
    return OkOut()
