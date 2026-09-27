from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["own", "aisensy"]
APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_ENV: str = "dev"
    APP_BASE_URL: str = "http://localhost:8000"
    DATABASE_URL: str = "postgresql+asyncpg://botdesk:botdesk@localhost:5432/botdesk"
    JWT_SECRET: str = "change-me"
    JWT_EXPIRE_MINUTES: int = 10080
    FERNET_KEY: str = ""
    ADMIN_EMAIL: str = "admin@example.com"
    ADMIN_PASSWORD: str = "change-me"
    CORS_ORIGINS: str = "http://localhost:5173"
    LOG_LEVEL: str = "INFO"
    SCHEDULER_ENABLED: bool = True

    # Provider switch
    WHATSAPP_PROVIDER: ProviderName = "own"

    # Meta Cloud API
    META_GRAPH_BASE: str = "https://graph.facebook.com"
    META_GRAPH_VERSION: str = "v23.0"
    META_APP_SECRET: str = ""
    META_WEBHOOK_VERIFY_TOKEN: str = ""

    # AiSensy
    AISENSY_API_BASE: str = "https://apis.aisensy.com/project-apis/v1"

    # AI (OpenRouter)
    OPENROUTER_API_KEY: str = ""
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    AI_MODEL: str = "google/gemini-3.7-flash"
    AI_FALLBACK_MODEL: str = "deepseek/deepseek-v4.1-flash"
    AI_MAX_OUTPUT_TOKENS: int = 400
    AI_TEMPERATURE: float = 0.3
    AI_HISTORY_TURNS: int = 12
    AI_TIMEOUT_SECONDS: float = 25
    USD_TO_INR: float = 88

    # Behaviour
    BOT_REPLY_MAX_WORDS: int = 60
    HANDOFF_AUTO_RELEASE_HOURS: int = 12
    NIGHT_START_HOUR: int = Field(22, ge=0, le=23)
    NIGHT_END_HOUR: int = Field(8, ge=0, le=23)
    OWNER_ALERT_TEMPLATE: str = "new_lead_alert"
    OWNER_ALERT_TEMPLATE_LANG: str = "en"
    TRIAL_DAYS: int = 7

    # Webhook rate limit (per IP token bucket)
    WEBHOOK_RATE_PER_SEC: float = 20
    WEBHOOK_RATE_BURST: int = 100

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    def missing_required(self) -> list[str]:
        """Keys that must be set for the app to run with the active default provider."""
        required = ["DATABASE_URL", "JWT_SECRET", "FERNET_KEY", "OPENROUTER_API_KEY", "AI_MODEL"]
        if self.WHATSAPP_PROVIDER == "own":
            required += ["META_APP_SECRET", "META_WEBHOOK_VERIFY_TOKEN"]
        else:
            required += ["AISENSY_API_BASE"]
        missing = [k for k in required if not str(getattr(self, k) or "").strip()]
        if self.APP_ENV == "prod" and self.JWT_SECRET == "change-me":
            missing.append("JWT_SECRET (still the default 'change-me')")
        return missing

    def validate_startup(self) -> None:
        missing = self.missing_required()
        if missing:
            raise RuntimeError(
                "Bot Desk cannot start. Missing required settings for provider "
                f"'{self.WHATSAPP_PROVIDER}': {', '.join(missing)}"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
