from __future__ import annotations

import hashlib
import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.api.deps import SessionDep
from app.config import get_settings
from app.errors import AppError
from app.models import Client, ClientChannel, Provider, WebhookEvent
from app.ratelimit import webhook_rate_limit
from app.services.inbound import process_webhook_event
from app.services.providers.factory import get_provider_by_name

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"], dependencies=[Depends(webhook_rate_limit)])


class WebhookAck(BaseModel):
    ok: bool = True
    duplicate: bool = False


def _parse_json(raw: bytes) -> dict:
    try:
        payload = json.loads(raw or b"{}")
    except ValueError as exc:
        raise AppError(400, "bad_request", "Body is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise AppError(400, "bad_request", "Body must be a JSON object")
    return payload


async def store_event(
    session: SessionDep, provider: str, raw: bytes, payload: dict, client_id: uuid.UUID | None = None
) -> uuid.UUID | None:
    """Persist the raw event. Returns its id, or None if this exact body was already received."""
    event_key = f"{provider}:{hashlib.sha256(raw).hexdigest()}"
    new_id = uuid.uuid4()
    inserted = await session.scalar(
        pg_insert(WebhookEvent)
        .values(id=new_id, provider=provider, event_key=event_key, client_id=client_id, payload=payload)
        .on_conflict_do_nothing(index_elements=["event_key"])
        .returning(WebhookEvent.id)
    )
    await session.commit()
    return inserted


@router.get("/meta", response_class=PlainTextResponse, summary="Meta webhook verification")
async def meta_verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
) -> PlainTextResponse:
    expected = get_settings().META_WEBHOOK_VERIFY_TOKEN
    if mode == "subscribe" and expected and token == expected:
        return PlainTextResponse(challenge)
    raise AppError(403, "forbidden", "Verification failed")


@router.post("/meta", response_model=WebhookAck, summary="Meta webhook receiver")
async def meta_receive(request: Request, background: BackgroundTasks, session: SessionDep) -> WebhookAck:
    raw = await request.body()
    provider = get_provider_by_name(Provider.own)
    if not provider.verify_signature(raw, request.headers, None):
        log.warning("meta_bad_signature")
        raise AppError(401, "invalid_signature", "Invalid X-Hub-Signature-256")
    payload = _parse_json(raw)
    event_id = await store_event(session, Provider.own.value, raw, payload)
    if event_id is None:
        return WebhookAck(duplicate=True)
    background.add_task(process_webhook_event, event_id)
    return WebhookAck()


@router.post(
    "/aisensy/{channel_token}", response_model=WebhookAck, summary="AiSensy project webhook receiver"
)
async def aisensy_receive(
    channel_token: str, request: Request, background: BackgroundTasks, session: SessionDep
) -> WebhookAck:
    raw = await request.body()
    channel = await session.scalar(
        select(ClientChannel).where(
            ClientChannel.channel_token == channel_token, ClientChannel.is_active.is_(True)
        )
    )
    client = await session.get(Client, channel.client_id) if channel else None
    if channel is None or client is None or client.deleted_at is not None:
        # Same response as a bad signature: don't reveal which tokens exist.
        raise AppError(401, "invalid_signature", "Unknown channel token or bad signature")
    provider = get_provider_by_name(Provider.aisensy)
    if not provider.verify_signature(raw, request.headers, channel):
        log.warning("aisensy_bad_signature", extra={"client_id": str(channel.client_id)})
        raise AppError(401, "invalid_signature", "Unknown channel token or bad signature")
    payload = _parse_json(raw)
    event_id = await store_event(session, Provider.aisensy.value, raw, payload, client_id=channel.client_id)
    if event_id is None:
        return WebhookAck(duplicate=True)
    background.add_task(process_webhook_event, event_id)
    return WebhookAck()
