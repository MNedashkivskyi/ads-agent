"""Measurement Foundation API — Phase 0 measurement-health diagnostic."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["measurement"])


class MeasurementSubScoreResponse(BaseModel):
    key: str
    label: str
    status: str
    detail: str


class ConversionActionSummaryResponse(BaseModel):
    name: str
    category: str
    status: str
    all_conversions: float
    health: str


class MeasurementHealthResponse(BaseModel):
    overall_status: str
    subscores: list[MeasurementSubScoreResponse]
    conversion_actions: list[ConversionActionSummaryResponse]


@router.get("/{user_id}/measurement/health", response_model=MeasurementHealthResponse)
async def get_measurement_health(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeasurementHealthResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import uuid

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.assess_measurement_health import (
        assess_measurement_health,
    )
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.models import GA4CredentialsModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)

            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            account = accounts[0]
            credentials = await credentials_repo.get(AccountId(account.id))
            if credentials is None:
                raise HTTPException(status_code=422, detail="Google Ads account not connected")

            google_ads = GoogleAdsQueriesAdapter(settings)
            snapshots = await google_ads.list_conversion_actions(
                credentials.refresh_token, account.customer_id
            )

            ga4_linked = (
                await session.execute(
                    select(GA4CredentialsModel.id).where(
                        GA4CredentialsModel.account_id == uuid.UUID(str(account.id))
                    )
                )
            ).scalar_one_or_none() is not None

            report = assess_measurement_health(snapshots, ga4_linked=ga4_linked)
    finally:
        await engine.dispose()

    logger.info(
        "measurement_health.complete",
        user_id=user_id,
        overall=report.overall_status.value,
        actions=len(report.conversion_actions),
        ga4_linked=ga4_linked,
    )

    return MeasurementHealthResponse(
        overall_status=report.overall_status.value,
        subscores=[
            MeasurementSubScoreResponse(
                key=s.key, label=s.label, status=s.status.value, detail=s.detail
            )
            for s in report.subscores
        ],
        conversion_actions=[
            ConversionActionSummaryResponse(
                name=c.name,
                category=c.category,
                status=c.status,
                all_conversions=c.all_conversions,
                health=c.health,
            )
            for c in report.conversion_actions
        ],
    )
