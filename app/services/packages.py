from __future__ import annotations

from decimal import Decimal

from app.models import Niche, Package

PACKAGES: dict[str, dict] = {
    Package.starter.value: {
        "setup": Decimal("3999.00"),
        "monthly": Decimal("1999.00"),
        "includes": [
            "WhatsApp AI assistant on one number",
            "English + one Indian language",
            "Knowledge base setup (prices, timings, FAQs)",
            "Lead capture with owner alerts",
            "Monthly report",
        ],
    },
    Package.business.value: {
        "setup": Decimal("7999.00"),
        "monthly": Decimal("3999.00"),
        "includes": [
            "Everything in Starter",
            "Up to three languages including Tanglish",
            "Booking / order collection flow",
            "Human handoff with inbox",
            "Two knowledge updates per month",
        ],
    },
    Package.growth.value: {
        "setup": Decimal("12999.00"),
        "monthly": Decimal("6999.00"),
        "includes": [
            "Everything in Business",
            "All Indian languages",
            "Priority support and weekly tuning",
            "Unlimited knowledge updates",
            "Detailed monthly review call",
        ],
    },
}

LANGUAGES = [
    "English",
    "Tamil",
    "Tanglish",
    "Hindi",
    "Hinglish",
    "Telugu",
    "Kannada",
    "Malayalam",
    "Marathi",
    "Bengali",
    "Gujarati",
    "Punjabi",
    "Odia",
    "Urdu",
]

NICHES = [n.value for n in Niche]


def default_fees(package: Package | str) -> tuple[Decimal, Decimal] | None:
    p = PACKAGES.get(Package(package).value)
    if p is None:
        return None
    return p["setup"], p["monthly"]
