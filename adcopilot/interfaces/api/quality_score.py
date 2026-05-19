"""Quality Score diagnostic API."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["quality-score"])


class KeywordQSItem(BaseModel):
    criterion_id: int
    text: str
    match_type: str
    quality_score: int | None
    expected_ctr: str | None
    ad_relevance: str | None
    landing_page_experience: str | None
    impressions: int


class QSDiagnosisResponse(BaseModel):
    keywords: list[KeywordQSItem]
    llm_summary: str | None
    avg_quality_score: float | None


class QSHistoryPoint(BaseModel):
    recorded_date: str
    quality_score: int | None
    expected_ctr: str | None
    ad_relevance: str | None
    landing_page_experience: str | None


class KeywordQSTrend(BaseModel):
    criterion_id: int
    keyword_text: str
    match_type: str
    history: list[QSHistoryPoint]


class QSTrendResponse(BaseModel):
    keywords: list[KeywordQSTrend]


@router.get("/{user_id}/quality-score/history", response_model=QSTrendResponse)
async def get_qs_history(
    user_id: str,
    current_user: CurrentUser,
) -> QSTrendResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from collections import defaultdict
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.account_repository import AccountRepository
    from adcopilot.infrastructure.db.repositories.keyword_qs_history_repository import (
        KeywordQSHistoryRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = AccountRepository(session)
            accounts = await account_repo.list_for_user(user_id)
            if not accounts:
                raise HTTPException(status_code=404, detail="No accounts found")

            account = accounts[0]
            repo = KeywordQSHistoryRepository(session)
            rows = await repo.get_latest_per_keyword(str(account.id), limit=50)

            # For top 20 keywords by most-recent date, fetch full history
            criterion_ids = list({r.criterion_id for r in rows})[:20]
            trends: dict[int, KeywordQSTrend] = {}
            for cid in criterion_ids:
                history_rows = await repo.get_history_for_keyword(str(account.id), cid, limit=30)
                if not history_rows:
                    continue
                latest = history_rows[0]
                trends[cid] = KeywordQSTrend(
                    criterion_id=cid,
                    keyword_text=latest.keyword_text,
                    match_type=latest.match_type,
                    history=[
                        QSHistoryPoint(
                            recorded_date=str(h.recorded_date),
                            quality_score=h.quality_score,
                            expected_ctr=h.expected_ctr,
                            ad_relevance=h.ad_relevance,
                            landing_page_experience=h.landing_page_experience,
                        )
                        for h in reversed(history_rows)
                    ],
                )
    finally:
        await engine.dispose()

    return QSTrendResponse(keywords=list(trends.values()))


@router.get("/{user_id}/quality-score/diagnose", response_model=QSDiagnosisResponse)
async def get_qs_diagnosis(
    user_id: str,
    current_user: CurrentUser,
) -> QSDiagnosisResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.diagnose_quality_score import diagnose_quality_score
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.account_repository import AccountRepository

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = AccountRepository(session)
            accounts = await account_repo.list_for_user(user_id)
            if not accounts:
                raise HTTPException(status_code=404, detail="No accounts found")

            account = accounts[0]
            result = await diagnose_quality_score(str(account.id), session)
    finally:
        await engine.dispose()

    return QSDiagnosisResponse(
        keywords=[
            KeywordQSItem(
                criterion_id=kw.criterion_id,
                text=kw.text,
                match_type=kw.match_type,
                quality_score=kw.quality_score,
                expected_ctr=kw.expected_ctr,
                ad_relevance=kw.ad_relevance,
                landing_page_experience=kw.landing_page_experience,
                impressions=kw.impressions,
            )
            for kw in result.keywords
        ],
        llm_summary=result.llm_summary,
        avg_quality_score=result.avg_quality_score,
    )
