"""Shared setup for inbound-pipeline tests: a client with an approved knowledge base and a channel."""

from __future__ import annotations

import hashlib
import hmac
import itertools
import json
from datetime import date

import httpx

from app.models import Client, ClientChannel, ClientStatus, KnowledgeBase, Niche, Provider
from app.security import encrypt_secret

META_SEND_URL = "https://graph.test/v23.0/PNID1/messages"
CUSTOMER = "919876543210"
OWNER = "919840012345"

_ids = itertools.count(1)


def meta_ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, json={"messaging_product": "whatsapp", "messages": [{"id": f"wamid.OUT_{next(_ids)}"}]}
    )


def meta_text_payload(body: str, msg_id: str, wa_id: str = CUSTOMER, name: str = "Ravi") -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "919840000001", "phone_number_id": "PNID1"},
                            "contacts": [{"profile": {"name": name}, "wa_id": wa_id}],
                            "messages": [
                                {
                                    "from": wa_id,
                                    "id": msg_id,
                                    "timestamp": "1790000000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    raw = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"test-app-secret", raw, hashlib.sha256).hexdigest()
    return raw, {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}


async def make_client(
    session,
    *,
    status: ClientStatus = ClientStatus.trial,
    approved: bool = True,
    with_kb: bool = True,
    provider_override: Provider | None = None,
) -> tuple[Client, ClientChannel]:
    client = Client(
        name="Smile Care Dental",
        niche=Niche.dental_clinic,
        city="Chennai",
        owner_name="Dr. Priya",
        owner_phone=f"+{OWNER}",
        status=status,
        live_date=date(2026, 1, 1) if status == ClientStatus.live else None,
        languages=["English", "Tamil"],
        provider_override=provider_override,
    )
    session.add(client)
    await session.flush()
    if with_kb:
        session.add(
            KnowledgeBase(
                client_id=client.id,
                address="Anna Nagar, Chennai",
                timings="10 AM – 9 PM",
                services="Consultation: ₹300\nScaling & polishing: ₹1,200",
                faqs="Q: Parking? A: Yes.",
                booking_instructions="Collect name and time.",
                rules="Never diagnose.",
                handoff_contact="+91 98400 12345",
                tone="Warm",
                approved=approved,
                version=1,
            )
        )
    channel = ClientChannel(
        client_id=client.id,
        provider=provider_override or Provider.own,
        meta_phone_number_id="PNID1",
        meta_access_token_enc=encrypt_secret("EAAG-test-token"),
        aisensy_project_id="proj_1",
        aisensy_api_key_enc=encrypt_secret("aisensy-pwd"),
        aisensy_webhook_secret_enc=encrypt_secret("aisensy-secret"),
        channel_token="chan-token-1",
        is_active=True,
    )
    session.add(channel)
    await session.commit()
    return client, channel
