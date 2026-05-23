"""Seasonality forecast API — 12-month history and next-30-day event preview."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["seasonality"])


class SeasonalEvent(BaseModel):
    date: str
    event_name_pl: str
    type: str
    recommended_budget_change_pct: float
    confidence: float


class MonthlyHistory(BaseModel):
    month: str
    spend_micros: int
    clicks: int
    conversions: float
    multiplier: float


class SeasonalityForecastResponse(BaseModel):
    account_id: str
    monthly_history: list[MonthlyHistory]
    upcoming_events: list[SeasonalEvent]
    recommendations_pl: str
    generated_at: str


@router.get("/{user_id}/seasonality/forecast", response_model=SeasonalityForecastResponse)
async def get_seasonality_forecast(
    user_id: str,
    current_user: CurrentUser,
) -> SeasonalityForecastResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.forecast_seasonality import forecast_seasonality
    from adcopilot.config import get_settings
    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            account_id = accounts[0].id
            llm = AnthropicClient(api_key=settings.LLM_API_KEY)
            prompt_repo = SqlPromptVersionRepository(session)
            result = await forecast_seasonality(
                account_id=account_id,
                session=session,
                llm=llm,
                prompt_repo=prompt_repo,
            )
    finally:
        await engine.dispose()

    return SeasonalityForecastResponse(
        account_id=result["account_id"],
        monthly_history=[MonthlyHistory(**m) for m in result["monthly_history"]],
        upcoming_events=[SeasonalEvent(**e) for e in result["upcoming_events"]],
        recommendations_pl=result["recommendations_pl"],
        generated_at=result["generated_at"],
    )


@router.get("/{user_id}/seasonality/upcoming", response_model=list[SeasonalEvent])
async def get_upcoming_seasonal_events(
    user_id: str,
    current_user: CurrentUser,
) -> list[SeasonalEvent]:
    """Return only next-30-day seasonal events — lightweight subset of the full forecast."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.forecast_seasonality import forecast_seasonality
    from adcopilot.config import get_settings
    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            account_id = accounts[0].id
            llm = AnthropicClient(api_key=settings.LLM_API_KEY)
            prompt_repo = SqlPromptVersionRepository(session)
            result = await forecast_seasonality(
                account_id=account_id,
                session=session,
                llm=llm,
                prompt_repo=prompt_repo,
            )
    finally:
        await engine.dispose()

    return [SeasonalEvent(**e) for e in result["upcoming_events"]]
