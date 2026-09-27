from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class KnowledgeIn(BaseModel):
    address: str | None = None
    timings: str | None = None
    services: str | None = Field(None, description="One service per line, with ₹ prices")
    faqs: str | None = None
    booking_instructions: str | None = None
    rules: str | None = Field(None, description="Never-say topics and hand-over topics")
    handoff_contact: str | None = None
    tone: str | None = None
    note: str | None = Field(None, description="Optional note stored with this version")


class KnowledgeOut(ORMModel):
    id: uuid.UUID
    client_id: uuid.UUID
    address: str
    timings: str
    services: str
    faqs: str
    booking_instructions: str
    rules: str
    handoff_contact: str
    tone: str
    approved: bool
    approved_at: datetime | None
    approved_by_name: str | None
    version: int
    updated_at: datetime


class ApproveIn(BaseModel):
    approved_by_name: str = Field(min_length=1, max_length=255)


class KnowledgeVersionOut(ORMModel):
    id: uuid.UUID
    version: int
    content: dict[str, str]
    saved_by: str | None
    note: str | None
    created_at: datetime


class KnowledgeTemplateOut(BaseModel):
    niche: str
    sample_business: str
    label: str
    knowledge: dict[str, str]
