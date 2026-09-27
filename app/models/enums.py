from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    admin = "admin"
    staff = "staff"


class Niche(StrEnum):
    dental_clinic = "dental_clinic"
    skin_clinic = "skin_clinic"
    salon = "salon"
    coaching_centre = "coaching_centre"
    gym = "gym"
    bakery_sweets = "bakery_sweets"
    real_estate = "real_estate"
    restaurant = "restaurant"
    other = "other"


class ClientStatus(StrEnum):
    lead = "lead"
    trial = "trial"
    live = "live"
    paused = "paused"


class Package(StrEnum):
    starter = "starter"
    business = "business"
    growth = "growth"
    custom = "custom"


class Provider(StrEnum):
    own = "own"
    aisensy = "aisensy"


class Direction(StrEnum):
    inbound = "in"
    outbound = "out"


class Sender(StrEnum):
    customer = "customer"
    bot = "bot"
    agent = "agent"
    system = "system"


class MsgType(StrEnum):
    text = "text"
    image = "image"
    audio = "audio"
    location = "location"
    template = "template"
    other = "other"


class MsgStatus(StrEnum):
    received = "received"
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class LeadStatus(StrEnum):
    new = "new"
    contacted = "contacted"
    won = "won"
    lost = "lost"


class PaymentType(StrEnum):
    setup = "setup"
    monthly = "monthly"
    other = "other"


class PaymentMethod(StrEnum):
    upi = "UPI"
    cash = "cash"
    bank = "bank"
    card = "card"
