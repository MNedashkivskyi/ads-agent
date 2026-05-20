"""Account structure analysis API endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["account-structure"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StructureIssueResponse(BaseModel):
    type: str
    severity: str
    description_pl: str
    affected_campaigns: list[str]
    recommendation_pl: str


class CampaignTreeNode(BaseModel):
    campaign_id: str
    campaign_name: str
    spend_micros: int
    clicks: int
    impressions: int
    conversions: float
    ad_group_count: int


class AccountStructureResponse(BaseModel):
    account_id: str
    campaign_count: int
    issues: list[StructureIssueResponse]
    tree: list[CampaignTreeNode]
    analyzed_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_account_id_for_user(user_id: str, settings: Settings) -> str:
    """Return the UUID of the first Google Ads account linked to user_id."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlGoogleAdsAccountRepository(session)
            accounts = await repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="Nie znaleziono konta Google Ads")
            return str(accounts[0].id)
    finally:
        await engine.dispose()


async def _run_analysis(user_id: str, settings: Settings) -> AccountStructureResponse:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.analyze_account_structure import (
        analyze_account_structure,
    )

    account_id = await _get_account_id_for_user(user_id, settings)

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            result = await analyze_account_structure(
                account_id=account_id,
                session=session,
            )
    finally:
        await engine.dispose()

    return AccountStructureResponse(
        account_id=result["account_id"],
        campaign_count=result["campaign_count"],
        issues=[
            StructureIssueResponse(
                type=issue["type"],
                severity=issue["severity"],
                description_pl=issue["description_pl"],
                affected_campaigns=issue["affected_campaigns"],
                recommendation_pl=issue["recommendation_pl"],
            )
            for issue in result["issues"]
        ],
        tree=[
            CampaignTreeNode(
                campaign_id=node["campaign_id"],
                campaign_name=node["campaign_name"],
                spend_micros=node["spend_micros"],
                clicks=node["clicks"],
                impressions=node["impressions"],
                conversions=node["conversions"],
                ad_group_count=node["ad_group_count"],
            )
            for node in result["tree"]
        ],
        analyzed_at=result["analyzed_at"],
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/{user_id}/account-structure/analysis",
    response_model=AccountStructureResponse,
)
async def get_account_structure_analysis(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountStructureResponse:
    """Analyze account structure and return detected issues together with the campaign tree."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    return await _run_analysis(user_id, settings)


@router.get(
    "/{user_id}/account-structure/tree",
    response_model=list[CampaignTreeNode],
)
async def get_account_structure_tree(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[CampaignTreeNode]:
    """Return only the campaign tree with aggregated 30-day metrics."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    response = await _run_analysis(user_id, settings)
    return response.tree
