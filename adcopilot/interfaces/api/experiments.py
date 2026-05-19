"""Ad experiment API endpoints — list, cancel experiments."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["experiments"])


class ExperimentMetrics(BaseModel):
    impressions: float
    clicks: float
    conversions: float
    ctr: float
    conversion_rate: float


class ExperimentResponse(BaseModel):
    id: str
    account_id: str
    campaign_resource_name: str
    ad_group_resource_name: str
    control_ad_resource_name: str
    variant_ad_resource_name: str
    status: str
    min_impressions: int
    confidence_threshold: float
    winner: str | None
    control_metrics: ExperimentMetrics | None
    variant_metrics: ExperimentMetrics | None
    started_at: str | None
    concluded_at: str | None
    created_at: str


def _to_metrics(raw: dict | None) -> ExperimentMetrics | None:
    if not raw:
        return None
    imp = float(raw.get("impressions", 0))
    clicks = float(raw.get("clicks", 0))
    conv = float(raw.get("conversions", 0))
    return ExperimentMetrics(
        impressions=imp,
        clicks=clicks,
        conversions=conv,
        ctr=clicks / imp if imp > 0 else 0.0,
        conversion_rate=conv / imp if imp > 0 else 0.0,
    )


@router.get(
    "/{user_id}/experiments",
    response_model=list[ExperimentResponse],
)
async def list_experiments(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[ExperimentResponse]:
    """List all experiments (running and concluded) for the user's account."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.repositories.ad_experiment_repository import (
        AdExperimentRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                return []

            exp_repo = AdExperimentRepository(session)
            all_exps = []
            for account in accounts:
                exps = await exp_repo.list_for_account(str(account.id))
                all_exps.extend(exps)
    finally:
        await engine.dispose()

    return [
        ExperimentResponse(
            id=str(e.id),
            account_id=str(e.account_id),
            campaign_resource_name=e.campaign_resource_name,
            ad_group_resource_name=e.ad_group_resource_name,
            control_ad_resource_name=e.control_ad_resource_name,
            variant_ad_resource_name=e.variant_ad_resource_name,
            status=e.status,
            min_impressions=e.min_impressions,
            confidence_threshold=e.confidence_threshold,
            winner=e.winner,
            control_metrics=_to_metrics(e.control_metrics),
            variant_metrics=_to_metrics(e.variant_metrics),
            started_at=e.started_at.isoformat() if e.started_at else None,
            concluded_at=e.concluded_at.isoformat() if e.concluded_at else None,
            created_at=e.created_at.isoformat(),
        )
        for e in all_exps
    ]


@router.post(
    "/{user_id}/experiments/{experiment_id}/cancel",
    response_model=ExperimentResponse,
)
async def cancel_experiment(
    user_id: str,
    experiment_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ExperimentResponse:
    """Cancel a running experiment (keeps both ads running but marks as cancelled)."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.ad_experiment_repository import (
        AdExperimentRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            exp_repo = AdExperimentRepository(session)
            exp = await exp_repo.get(experiment_id)
            if exp is None:
                raise HTTPException(status_code=404, detail="Experiment not found")
            if exp.status != "running":
                raise HTTPException(status_code=409, detail=f"Experiment is already {exp.status}")

            now = datetime.now(UTC)
            await exp_repo.cancel(experiment_id, concluded_at=now)
            exp.status = "cancelled"
            exp.concluded_at = now
    finally:
        await engine.dispose()

    return ExperimentResponse(
        id=str(exp.id),
        account_id=str(exp.account_id),
        campaign_resource_name=exp.campaign_resource_name,
        ad_group_resource_name=exp.ad_group_resource_name,
        control_ad_resource_name=exp.control_ad_resource_name,
        variant_ad_resource_name=exp.variant_ad_resource_name,
        status=exp.status,
        min_impressions=exp.min_impressions,
        confidence_threshold=exp.confidence_threshold,
        winner=exp.winner,
        control_metrics=_to_metrics(exp.control_metrics),
        variant_metrics=_to_metrics(exp.variant_metrics),
        started_at=exp.started_at.isoformat() if exp.started_at else None,
        concluded_at=exp.concluded_at.isoformat() if exp.concluded_at else None,
        created_at=exp.created_at.isoformat(),
    )
