from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth,
    billing,
    channels,
    clients,
    config,
    dashboard,
    health,
    inbox,
    knowledge,
    leads,
    payments,
    test_chat,
    webhooks,
)
from app.config import APP_VERSION, get_settings
from app.db import engine
from app.errors import install_error_handlers
from app.jobs.scheduler import build_scheduler
from app.logging_setup import RequestIdMiddleware, configure_logging

log = logging.getLogger(__name__)

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_startup()
    log.info("startup", extra={"provider": settings.WHATSAPP_PROVIDER, "env": settings.APP_ENV})
    scheduler = None
    if settings.SCHEDULER_ENABLED:
        scheduler = build_scheduler()
        scheduler.start()
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.LOG_LEVEL)
    app = FastAPI(
        title="Bot Desk API",
        version=APP_VERSION,
        description="WhatsApp AI assistants for local businesses: clients, knowledge, inbox, billing.",
        lifespan=lifespan,
    )
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(webhooks.router)
    for module in (
        auth,
        config,
        clients,
        knowledge,
        channels,
        test_chat,
        inbox,
        leads,
        payments,
        billing,
        dashboard,
    ):
        app.include_router(module.router, prefix=API_PREFIX)
    return app


app = create_app()
