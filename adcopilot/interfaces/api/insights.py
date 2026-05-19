"""Insight history API endpoint — GET /api/{user_id}/insights."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["insights"])


class InsightItem(BaseModel):
    id: str
    account_id: str | None
    week_start: str
    insight_text: str
    created_at: str


class InsightHistoryResponse(BaseModel):
    items: list[InsightItem]
    limit: int
    offset: int


@router.get("/{user_id}/insights", response_model=InsightHistoryResponse)
async def list_insights(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> InsightHistoryResponse:
    """Return paginated weekly insight history for the user, most recent first."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.weekly_insight_repository import (
        SqlWeeklyInsightRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlWeeklyInsightRepository(session)
            insights = await repo.list_for_user(user_id=user_id, limit=limit, offset=offset)
    finally:
        await engine.dispose()

    return InsightHistoryResponse(
        items=[
            InsightItem(
                id=i.id,
                account_id=i.account_id,
                week_start=i.week_start.isoformat(),
                insight_text=i.insight_text,
                created_at=i.created_at.isoformat(),
            )
            for i in insights
        ],
        limit=limit,
        offset=offset,
    )
