from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings


def _make_engine() -> AsyncEngine:
    settings = get_settings()
    kwargs: dict = {"pool_pre_ping": True}
    if settings.APP_ENV == "test":
        # Tests run each case on its own event loop; pooled asyncpg connections can't cross loops.
        kwargs = {"poolclass": NullPool}
    return create_async_engine(settings.DATABASE_URL, **kwargs)


engine: AsyncEngine = _make_engine()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
