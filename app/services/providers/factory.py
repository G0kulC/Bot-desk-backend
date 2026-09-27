"""The only place that maps a client to a WhatsApp provider implementation."""

from __future__ import annotations

from typing import Protocol

from app.config import get_settings
from app.models import Provider
from app.services.providers.aisensy import AiSensyProvider
from app.services.providers.base import WhatsAppProvider
from app.services.providers.meta_cloud import MetaCloudProvider


class _HasOverride(Protocol):
    provider_override: Provider | str | None


_REGISTRY: dict[Provider, WhatsAppProvider] = {}


def _build(name: Provider) -> WhatsAppProvider:
    if name == Provider.own:
        return MetaCloudProvider()
    if name == Provider.aisensy:
        return AiSensyProvider()
    raise ValueError(f"Unknown WhatsApp provider: {name}")


def get_provider_by_name(name: Provider | str) -> WhatsAppProvider:
    key = Provider(name)
    if key not in _REGISTRY:
        _REGISTRY[key] = _build(key)
    return _REGISTRY[key]


def effective_provider(client: _HasOverride) -> Provider:
    """client.provider_override wins; otherwise the WHATSAPP_PROVIDER env default."""
    return Provider(client.provider_override or get_settings().WHATSAPP_PROVIDER)


def get_provider(client: _HasOverride) -> WhatsAppProvider:
    return get_provider_by_name(effective_provider(client))
