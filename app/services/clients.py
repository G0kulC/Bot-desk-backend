from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import not_found
from app.models import Client, ClientChannel


async def get_client_or_404(session: AsyncSession, client_id: uuid.UUID) -> Client:
    client = await session.get(Client, client_id)
    if client is None or client.deleted_at is not None:
        raise not_found("Client")
    return client


async def get_active_channel(session: AsyncSession, client_id: uuid.UUID) -> ClientChannel | None:
    return await session.scalar(
        select(ClientChannel).where(ClientChannel.client_id == client_id, ClientChannel.is_active.is_(True))
    )
