from __future__ import annotations

import os

from cryptography.fernet import Fernet

# Configure the app for tests before anything imports app.config.
os.environ.update(
    {
        "APP_ENV": "test",
        "DATABASE_URL": os.environ.get(
            "TEST_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/bots_db_v1_test"
        ),
        "FERNET_KEY": Fernet.generate_key().decode(),
        "JWT_SECRET": "test-jwt-secret-that-is-long-enough-for-hs256",
        "OPENROUTER_API_KEY": "test-openrouter-key",
        "OPENROUTER_BASE_URL": "https://openrouter.test/api/v1",
        "AI_MODEL": "primary/model",
        "AI_FALLBACK_MODEL": "fallback/model",
        "META_APP_SECRET": "test-app-secret",
        "META_WEBHOOK_VERIFY_TOKEN": "verify-me",
        "META_GRAPH_BASE": "https://graph.test",
        "META_GRAPH_VERSION": "v23.0",
        "AISENSY_API_BASE": "https://aisensy.test/project-apis/v1",
        "WHATSAPP_PROVIDER": "own",
        "APP_BASE_URL": "https://api.test",
        "SCHEDULER_ENABLED": "false",
        "WEBHOOK_RATE_BURST": "10000",
    }
)

import asyncio

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.models import Base

settings = get_settings()


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")


async def _reset_schema() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    await engine.dispose()


@pytest.fixture(scope="session")
def migrated_db() -> None:
    try:
        asyncio.run(_reset_schema())
    except Exception as exc:  # database not reachable
        pytest.skip(f"PostgreSQL not available at TEST_DATABASE_URL: {exc}")
    _run_migrations()


async def _truncate_all() -> None:
    engine = create_async_engine(settings.DATABASE_URL)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()


@pytest_asyncio.fixture
async def session(migrated_db):
    from app.db import SessionLocal

    await _truncate_all()
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def api(session):
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c


@pytest_asyncio.fixture
async def admin(session):
    from app.models import User, UserRole
    from app.security import hash_password

    user = User(
        email="admin@test.in",
        password_hash=hash_password("secret123"),
        full_name="Admin",
        role=UserRole.admin,
    )
    session.add(user)
    await session.commit()
    return user


@pytest_asyncio.fixture
async def auth(api, admin) -> dict[str, str]:
    r = await api.post("/api/v1/auth/login", json={"email": "admin@test.in", "password": "secret123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
