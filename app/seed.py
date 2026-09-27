"""Demo data. Run with: python -m app.seed  (idempotent: safe to run more than once)."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.config import get_settings
from app.db import SessionLocal, engine
from app.models import Client, ClientStatus, Niche, Package, User, UserRole
from app.security import hash_password
from app.seed_data import SAMPLE_LABEL, TEMPLATES
from app.services.knowledge import get_knowledge, save_knowledge
from app.services.packages import default_fees
from app.timeutil import today_ist

EXAMPLE_CLIENT = "Smile Care Dental (example)"


async def seed() -> None:
    s = get_settings()
    async with SessionLocal() as session:
        admin = await session.scalar(select(User).where(func.lower(User.email) == s.ADMIN_EMAIL.lower()))
        if admin is None:
            session.add(
                User(
                    email=s.ADMIN_EMAIL,
                    password_hash=hash_password(s.ADMIN_PASSWORD),
                    full_name="Admin",
                    role=UserRole.admin,
                    is_active=True,
                )
            )
            print(f"Created admin user {s.ADMIN_EMAIL}")
        else:
            print(f"Admin user {s.ADMIN_EMAIL} already exists (password unchanged)")

        client = await session.scalar(select(Client).where(Client.name == EXAMPLE_CLIENT))
        if client is None:
            setup, monthly = default_fees(Package.business) or (0, 0)
            client = Client(
                name=EXAMPLE_CLIENT,
                niche=Niche.dental_clinic,
                city="Chennai",
                owner_name="Dr. Example",
                owner_phone=None,
                status=ClientStatus.trial,
                package=Package.business,
                setup_fee=setup,
                monthly_fee=monthly,
                trial_start=today_ist(),
                languages=["English", "Tamil"],
                bot_enabled=True,
                notes=f"Example client with the dental sample knowledge. {SAMPLE_LABEL}.",
            )
            session.add(client)
            await session.flush()
            print(f"Created example client '{EXAMPLE_CLIENT}' (trial)")
        else:
            print(f"Example client '{EXAMPLE_CLIENT}' already exists")

        if await get_knowledge(session, client.id) is None:
            await save_knowledge(
                session,
                client.id,
                TEMPLATES["dental_clinic"]["knowledge"],
                saved_by="seed",
                note=SAMPLE_LABEL,
            )
            print("Added dental sample knowledge (not approved; trial clients still get replies)")

        await session.commit()

    print("Sample knowledge templates available at GET /api/v1/knowledge/templates/{niche}:")
    for niche, tpl in TEMPLATES.items():
        print(f"  - {niche}: {tpl['sample_business']} ({SAMPLE_LABEL})")
    await engine.dispose()


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
