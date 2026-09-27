from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentUser
from app.config import APP_VERSION, get_settings
from app.services.packages import LANGUAGES, NICHES, PACKAGES

router = APIRouter(prefix="/config", tags=["config"])


class PackageInfo(BaseModel):
    setup: Decimal
    monthly: Decimal
    includes: list[str]


class ConfigOut(BaseModel):
    default_provider: str
    ai_model: str
    ai_fallback_model: str
    packages: dict[str, PackageInfo]
    languages: list[str]
    niches: list[str]
    trial_days: int
    app_version: str


@router.get("", response_model=ConfigOut)
async def get_config(_: CurrentUser) -> ConfigOut:
    s = get_settings()
    return ConfigOut(
        default_provider=s.WHATSAPP_PROVIDER,
        ai_model=s.AI_MODEL,
        ai_fallback_model=s.AI_FALLBACK_MODEL,
        packages={k: PackageInfo(**v) for k, v in PACKAGES.items()},
        languages=LANGUAGES,
        niches=NICHES,
        trial_days=s.TRIAL_DAYS,
        app_version=APP_VERSION,
    )
