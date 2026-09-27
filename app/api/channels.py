from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.errors import AppError, not_found
from app.models import Client, ClientChannel, Provider
from app.security import encrypt_secret, new_channel_token, secret_hint
from app.services.audit import audit
from app.services.clients import get_active_channel, get_client_or_404
from app.services.phone import normalize_e164, to_wa_id
from app.services.providers.factory import effective_provider, get_provider

router = APIRouter(tags=["channels"])


class SecretHint(BaseModel):
    has_token: bool
    last4: str | None


class ChannelIn(BaseModel):
    display_phone: str | None = None
    meta_phone_number_id: str | None = None
    meta_waba_id: str | None = None
    meta_access_token: str | None = Field(None, description="Write-only. Send '' to clear.")
    aisensy_project_id: str | None = None
    aisensy_api_key: str | None = Field(None, description="Write-only AiSensy Project API password")
    aisensy_webhook_secret: str | None = Field(None, description="Write-only; used to verify signatures")
    is_active: bool | None = None
    rotate_channel_token: bool = False

    @field_validator("display_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        return normalize_e164(v) if v else v


class ChannelOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    provider: Provider
    effective_provider: Provider
    display_phone: str | None
    meta_phone_number_id: str | None
    meta_waba_id: str | None
    meta_access_token: SecretHint
    aisensy_project_id: str | None
    aisensy_api_key: SecretHint
    aisensy_webhook_secret: SecretHint
    is_active: bool
    last_inbound_at: datetime | None
    last_error: str | None
    webhook_url: str
    meta_verify_token_set: bool


class ChannelTestOut(BaseModel):
    ok: bool
    provider: str
    to: str
    provider_message_id: str | None
    status_code: int | None
    error: str | None
    response: dict | None


def webhook_url(client: Client, channel: ClientChannel) -> str:
    base = get_settings().APP_BASE_URL.rstrip("/")
    if effective_provider(client) == Provider.aisensy:
        return f"{base}/webhooks/aisensy/{channel.channel_token}"
    return f"{base}/webhooks/meta"


def channel_out(client: Client, ch: ClientChannel) -> ChannelOut:
    return ChannelOut(
        id=ch.id,
        client_id=ch.client_id,
        provider=ch.provider,
        effective_provider=effective_provider(client),
        display_phone=ch.display_phone,
        meta_phone_number_id=ch.meta_phone_number_id,
        meta_waba_id=ch.meta_waba_id,
        meta_access_token=SecretHint(**secret_hint(ch.meta_access_token_enc)),
        aisensy_project_id=ch.aisensy_project_id,
        aisensy_api_key=SecretHint(**secret_hint(ch.aisensy_api_key_enc)),
        aisensy_webhook_secret=SecretHint(**secret_hint(ch.aisensy_webhook_secret_enc)),
        is_active=ch.is_active,
        last_inbound_at=ch.last_inbound_at,
        last_error=ch.last_error,
        webhook_url=webhook_url(client, ch),
        meta_verify_token_set=bool(get_settings().META_WEBHOOK_VERIFY_TOKEN),
    )


@router.get("/clients/{client_id}/channel", response_model=ChannelOut)
async def get_channel(client_id: uuid.UUID, session: SessionDep, _: CurrentUser) -> ChannelOut:
    client = await get_client_or_404(session, client_id)
    ch = await get_active_channel(session, client_id)
    if ch is None:
        raise not_found("Channel")
    return channel_out(client, ch)


@router.put("/clients/{client_id}/channel", response_model=ChannelOut)
async def put_channel(
    client_id: uuid.UUID, body: ChannelIn, session: SessionDep, user: CurrentUser
) -> ChannelOut:
    client = await get_client_or_404(session, client_id)
    ch = await get_active_channel(session, client_id)
    created = ch is None
    if ch is None:
        ch = ClientChannel(client_id=client_id, channel_token=new_channel_token(), is_active=True)
        session.add(ch)
    ch.provider = effective_provider(client)
    data = body.model_dump(exclude_unset=True)
    for field in ("display_phone", "meta_phone_number_id", "meta_waba_id", "aisensy_project_id"):
        if field in data:
            setattr(ch, field, (data[field] or None))
    for field in ("meta_access_token", "aisensy_api_key", "aisensy_webhook_secret"):
        if field in data and data[field] is not None:
            setattr(ch, f"{field}_enc", encrypt_secret(data[field].strip()) if data[field].strip() else None)
    if data.get("rotate_channel_token"):
        ch.channel_token = new_channel_token()
    if body.is_active is not None:
        ch.is_active = body.is_active
    audit(
        session,
        user,
        "channel.create" if created else "channel.update",
        "client_channel",
        client_id,
        {k: ("***" if k in {"meta_access_token", "aisensy_api_key", "aisensy_webhook_secret"} else v)
         for k, v in data.items()},
    )  # fmt: skip
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AppError(
            409, "conflict", "That Meta phone number id is already used by another client"
        ) from exc
    await session.refresh(ch)
    return channel_out(client, ch)


@router.post("/clients/{client_id}/channel/test", response_model=ChannelTestOut)
async def test_channel(client_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> ChannelTestOut:
    """Send 'Bot Desk test message ✅' to the owner's phone and return the provider response."""
    client = await get_client_or_404(session, client_id)
    ch = await get_active_channel(session, client_id)
    if ch is None:
        raise not_found("Channel")
    owner = to_wa_id(client.owner_phone)
    if not owner:
        raise AppError(409, "owner_phone_missing", "Set the client's owner_phone first")
    provider = get_provider(client)
    result = await provider.send_text(ch, owner, "Bot Desk test message ✅")
    ch.last_error = None if result.ok else result.error
    audit(session, user, "channel.test", "client_channel", client_id, {"ok": result.ok})
    await session.commit()
    return ChannelTestOut(
        ok=result.ok,
        provider=provider.name,
        to=f"***{owner[-4:]}",
        provider_message_id=result.provider_message_id,
        status_code=result.status_code,
        error=result.error,
        response=result.raw,
    )
