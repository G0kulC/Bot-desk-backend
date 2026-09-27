from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.errors import AppError, not_found
from app.models import AttentionItem
from app.schemas.common import OkOut
from app.services.audit import audit
from app.services.clients import get_client_or_404
from app.services.reports import dashboard_summary, monthly_report, parse_month_or_current
from app.timeutil import utcnow

router = APIRouter(tags=["dashboard"])


class AttentionOut(BaseModel):
    id: uuid.UUID | None = None
    client_id: uuid.UUID | None
    kind: str
    text: str


class DashboardOut(BaseModel):
    paying_clients: int
    goal: int
    mrr: Decimal
    collected_this_month: Decimal
    overdue_amount: Decimal
    overdue_count: int
    trials_ending_7d: int
    leads_new_7d: int
    handoffs_open: int
    messages_7d: int
    ai_cost_inr_30d: Decimal
    pipeline: dict[str, int]
    attention: list[AttentionOut]


class QuestionCount(BaseModel):
    question: str
    count: int


class MonthlyReportOut(BaseModel):
    client_id: uuid.UUID
    month: str
    chats: int
    messages_in: int
    messages_out: int
    bot_replies: int
    agent_replies: int
    leads: int
    handoffs: int
    night_enquiries: int
    night_share: float
    top_questions: list[QuestionCount]
    languages: dict[str, int]
    avg_bot_reply_seconds: float | None
    ai_cost_inr: Decimal


@router.get("/dashboard/summary", response_model=DashboardOut)
async def summary(session: SessionDep, _: CurrentUser) -> dict:
    return await dashboard_summary(session)


@router.post("/dashboard/attention/{item_id}/resolve", response_model=OkOut)
async def resolve_attention(item_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> OkOut:
    item = await session.get(AttentionItem, item_id)
    if item is None:
        raise not_found("Attention item")
    item.resolved_at = utcnow()
    audit(session, user, "attention.resolve", "attention_item", item.id, {"kind": item.kind})
    await session.commit()
    return OkOut()


@router.get("/reports/monthly", response_model=MonthlyReportOut, tags=["reports"])
async def report(
    session: SessionDep,
    _: CurrentUser,
    client_id: uuid.UUID,
    month: str | None = Query(None, description="YYYY-MM (IST); defaults to the current month"),
) -> dict:
    await get_client_or_404(session, client_id)
    try:
        year, mon = parse_month_or_current(month)
    except ValueError as exc:
        raise AppError(422, "validation_error", str(exc)) from exc
    return await monthly_report(session, client_id, year, mon)
