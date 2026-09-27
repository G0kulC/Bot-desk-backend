from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.config import get_settings
from app.errors import AppError
from app.services.ai.engine import LeadInfo, generate_reply
from app.services.clients import get_client_or_404
from app.services.knowledge import get_knowledge

router = APIRouter(tags=["test-chat"])


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class TestChatIn(BaseModel):
    history: list[ChatTurn] = Field(default_factory=list)
    message: str = Field(min_length=1, max_length=4000)


class TestChatOut(BaseModel):
    reply: str
    language: str
    lead: LeadInfo | None
    handoff: bool
    handoff_reason: str | None
    model: str | None
    tokens_in: int
    tokens_out: int
    cost_inr: Decimal
    guardrail_notes: list[str]


@router.post("/clients/{client_id}/test-chat", response_model=TestChatOut)
async def test_chat(
    client_id: uuid.UUID, body: TestChatIn, session: SessionDep, _: CurrentUser
) -> TestChatOut:
    """Same AI engine and guardrails as live WhatsApp. Nothing is saved or sent."""
    client = await get_client_or_404(session, client_id)
    kb = await get_knowledge(session, client_id)
    if kb is None:
        raise AppError(409, "knowledge_missing", "Save the knowledge base before testing the assistant")
    s = get_settings()
    history = [t.model_dump() for t in body.history][-s.AI_HISTORY_TURNS :]
    user_text = "\n".join(t.content for t in body.history if t.role == "user") + "\n" + body.message
    result = await generate_reply(client, kb, history, body.message, extra_allowed_text=user_text)
    notes = list(result.guardrail_notes)
    if not kb.approved:
        notes.insert(0, "knowledge_not_approved: live clients would get a holding message instead")
    if not result.ok or result.reply is None:
        raise AppError(502, "ai_unavailable", "Both AI models failed: " + "; ".join(result.errors))
    if result.used_fallback:
        notes.append(f"fallback_model_used: {'; '.join(result.errors)}")
    cost_inr = (result.cost_usd * Decimal(str(s.USD_TO_INR))).quantize(Decimal("0.0001"))
    return TestChatOut(
        reply=result.reply.reply,
        language=result.reply.language,
        lead=result.reply.lead,
        handoff=result.reply.handoff,
        handoff_reason=result.reply.handoff_reason,
        model=result.model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cost_inr=cost_inr,
        guardrail_notes=notes,
    )
