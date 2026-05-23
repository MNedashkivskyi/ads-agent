"""Client Q&A API endpoint — POST /ask and GET /qa-history."""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser
from adcopilot.rate_limit import limiter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["qa"])

_QA_LIMIT = "10/hour"


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    account_id: str | None = None


class AskResponse(BaseModel):
    answer: str
    context_summary: dict[str, Any]


class QaHistoryItem(BaseModel):
    id: str
    question: str
    answer: str
    account_id: str | None
    created_at: str


class QaHistoryResponse(BaseModel):
    items: list[QaHistoryItem]
    limit: int
    offset: int


@router.post("/{user_id}/ask", response_model=AskResponse)
@limiter.limit(_QA_LIMIT)
async def ask(
    request: Request,
    user_id: str,
    body: AskRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AskResponse:
    """Answer a natural-language question about the user's Google Ads account."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.services.account_context_builder import AccountContextBuilder
    from adcopilot.application.use_cases.answer_client_question import AnswerClientQuestionUseCase
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.repositories.audit_log_repository import (
        SqlAuditLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )
    from adcopilot.infrastructure.db.repositories.qa_conversation_repository import (
        SqlQaConversationRepository,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import (
        SqlSnapshotRepository,
    )
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)

            if body.account_id:
                account = await account_repo.get(AccountId(body.account_id))
                if account is None or str(account.user_id) != user_id:
                    raise HTTPException(status_code=404, detail="Account not found")
                account_id = account.id
            else:
                accounts = await account_repo.list_for_user(UserId(user_id))
                if not accounts:
                    raise HTTPException(status_code=404, detail="No Google Ads accounts found")
                account_id = accounts[0].id

            snapshot_repo = SqlSnapshotRepository(session)
            rec_repo = SqlRecommendationRepository(session)
            audit_repo = SqlAuditLogRepository(session)
            prompt_repo = SqlPromptVersionRepository(session)
            qa_repo = SqlQaConversationRepository(session)

            builder = AccountContextBuilder(
                snapshot_repo=snapshot_repo,
                rec_repo=rec_repo,
                audit_log_repo=audit_repo,
            )
            ctx = await builder.build(account_id)

            llm = AnthropicClient(api_key=settings.LLM_API_KEY)
            use_case = AnswerClientQuestionUseCase(llm=llm, prompt_repo=prompt_repo)
            answer = await use_case.execute(question=body.question, account_context=ctx)

            await qa_repo.save(
                user_id=user_id,
                account_id=str(account_id) if account_id else None,
                question=body.question,
                answer=answer,
                context_snapshot={
                    "snapshot_date": ctx.get("snapshot_date"),
                    "summary": ctx.get("summary"),
                },
            )
    finally:
        await engine.dispose()

    context_summary = {
        "account_id": ctx.get("account_id"),
        "snapshot_date": ctx.get("snapshot_date"),
        "has_data": ctx.get("summary") is not None,
        "active_campaigns": ctx.get("summary", {}).get("active_campaigns")
        if ctx.get("summary")
        else 0,
    }

    return AskResponse(answer=answer, context_summary=context_summary)


@router.get("/{user_id}/qa-history", response_model=QaHistoryResponse)
async def qa_history(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> QaHistoryResponse:
    """Return paginated Q&A conversation history for the user, most recent first."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.qa_conversation_repository import (
        SqlQaConversationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            qa_repo = SqlQaConversationRepository(session)
            conversations = await qa_repo.list_for_user(user_id=user_id, limit=limit, offset=offset)
    finally:
        await engine.dispose()

    return QaHistoryResponse(
        items=[
            QaHistoryItem(
                id=c.id,
                question=c.question,
                answer=c.answer,
                account_id=c.account_id,
                created_at=c.created_at.isoformat(),
            )
            for c in conversations
        ],
        limit=limit,
        offset=offset,
    )
