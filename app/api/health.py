from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session

router = APIRouter(tags=["health"])


class HealthOut(BaseModel):
    status: str
    db: bool
    default_provider: str


@router.get("/health", response_model=HealthOut)
async def health(session: AsyncSession = Depends(get_session)) -> HealthOut:
    try:
        await session.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    return HealthOut(
        status="ok" if db_ok else "degraded", db=db_ok, default_provider=get_settings().WHATSAPP_PROVIDER
    )
