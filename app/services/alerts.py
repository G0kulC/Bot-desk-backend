"""Owner alerts (new lead, handoff, AI failure, unapproved knowledge).

Sent to client.owner_phone through the client's provider: free-form text if the owner messaged
this business number in the last 24 hours, otherwise the approved utility template
OWNER_ALERT_TEMPLATE with params [customer name, customer number, need/reason, time].
Every alert is logged as a `system` message on the customer's conversation; failed sends stay
visible in the dashboard as undelivered.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Client, ClientChannel, Contact, Message, MsgType, Sender
from app.security import mask_phone
from app.services.messaging import record_outbound
from app.services.phone import to_wa_id
from app.services.providers.base import SendResult
from app.services.providers.factory import get_provider
from app.timeutil import fmt_ist, utcnow

ALERT_TITLES = {
    "lead": "New lead",
    "handoff": "Customer needs a person",
    "ai_failed": "Assistant could not reply",
    "kb_not_approved": "Knowledge not approved – bot sent a holding reply",
}


async def owner_in_window(session: AsyncSession, client: Client, owner_wa: str) -> bool:
    last = await session.scalar(
        select(Contact.last_inbound_at).where(Contact.client_id == client.id, Contact.wa_id == owner_wa)
    )
    return last is not None and last >= utcnow() - timedelta(hours=24)


async def alert_owner(
    session: AsyncSession,
    client: Client,
    channel: ClientChannel | None,
    contact: Contact,
    kind: str,
    detail: str,
) -> Message:
    s = get_settings()
    owner_wa = to_wa_id(client.owner_phone)
    customer_name = contact.profile_name or "Customer"
    customer_number = f"+{contact.wa_id}"
    when = fmt_ist(utcnow())
    title = ALERT_TITLES.get(kind, "Alert")
    text = (
        f"🔔 {title} – {client.name}\nCustomer: {customer_name} ({customer_number})\n{detail}\nTime: {when}"
    )

    via = "text"
    if not owner_wa:
        result = SendResult(ok=False, error="Client has no owner_phone")
    elif channel is None:
        result = SendResult(ok=False, error="No active WhatsApp channel for this client")
    else:
        provider = get_provider(client)
        if await owner_in_window(session, client, owner_wa):
            result = await provider.send_text(channel, owner_wa, text)
        else:
            via = "template"
            result = await provider.send_template(
                channel,
                owner_wa,
                s.OWNER_ALERT_TEMPLATE,
                s.OWNER_ALERT_TEMPLATE_LANG,
                [customer_name, customer_number, detail[:900], when],
            )

    return record_outbound(
        session,
        client,
        channel,
        contact,
        text,
        Sender.system,
        result,
        msg_type=MsgType.template if via == "template" else MsgType.text,
        meta={
            "kind": "owner_alert",
            "alert_kind": kind,
            "to": mask_phone(owner_wa),
            "via": via,
            "undelivered": not result.ok,
        },
    )
