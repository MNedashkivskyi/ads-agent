"""PATCH endpoints for structured editing of campaign proposals.

Five endpoints:
  PATCH /api/proposals/{id}/budget          — change daily budget
  PATCH /api/proposals/{id}/keywords        — replace keywords in an ad group
  PATCH /api/proposals/{id}/ads             — replace ad copy in an ad group
  PATCH /api/proposals/{id}/targeting       — change location targeting
  POST  /api/proposals/{id}/regenerate-copy — re-run LLM copy for one ad group
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/proposals", tags=["proposal-editor"])

_MICROS_PER_PLN = 1_000_000


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class PatchBudgetRequest(BaseModel):
    monthly_budget_pln: float


class PatchKeywordsRequest(BaseModel):
    ad_group_index: int
    keywords: list[dict]  # [{text, match_type}]


class PatchAdsRequest(BaseModel):
    ad_group_index: int
    headlines: list[str]
    descriptions: list[str]


class PatchTargetingRequest(BaseModel):
    location_targeting: str


class RegenerateCopyRequest(BaseModel):
    ad_group_index: int


class EditResponse(BaseModel):
    proposal_id: str
    status: str = "updated"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DAILY_MULTIPLIER = Decimal("30.4")


def _monthly_to_daily_micros(monthly_pln: float) -> int:
    monthly = Decimal(str(monthly_pln))
    daily = monthly / _DAILY_MULTIPLIER
    return int(daily * _MICROS_PER_PLN)


async def _load_proposal(session, proposal_id: str, user_id: str):
    """Load proposal and verify ownership via brief.user_id."""
    from adcopilot.domain.launch.entities import CampaignBriefId, CampaignProposalId
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
        SqlCampaignProposalRepository,
    )

    proposal_repo = SqlCampaignProposalRepository(session)
    proposal = await proposal_repo.get(CampaignProposalId(proposal_id))
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    brief_repo = SqlCampaignBriefRepository(session)
    brief = await brief_repo.get(CampaignBriefId(str(proposal.brief_id)))
    if brief is None or brief.user_id != user_id:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return proposal, proposal_repo


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.patch("/{proposal_id}/budget", response_model=EditResponse)
async def patch_budget(
    proposal_id: str,
    body: PatchBudgetRequest,
    user_id: CurrentUser,
) -> EditResponse:
    """Update the campaign daily budget derived from a new monthly budget."""
    try:
        uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal ID") from None

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            proposal, repo = await _load_proposal(session, proposal_id, user_id)

            new_daily_micros = _monthly_to_daily_micros(body.monthly_budget_pln)
            from dataclasses import replace as dc_replace
            updated = dc_replace(proposal, daily_budget_micros=new_daily_micros)
            await repo.save(updated)
    finally:
        await engine.dispose()

    logger.info(
        "proposal.budget_patched",
        proposal_id=proposal_id,
        monthly_pln=body.monthly_budget_pln,
        user_id=user_id,
    )
    return EditResponse(proposal_id=proposal_id)


@router.patch("/{proposal_id}/targeting", response_model=EditResponse)
async def patch_targeting(
    proposal_id: str,
    body: PatchTargetingRequest,
    user_id: CurrentUser,
) -> EditResponse:
    """Update the location targeting string on a campaign proposal."""
    try:
        uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal ID") from None

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            proposal, repo = await _load_proposal(session, proposal_id, user_id)
            from dataclasses import replace as dc_replace
            updated = dc_replace(proposal, location_targeting=body.location_targeting.strip())
            await repo.save(updated)
    finally:
        await engine.dispose()

    logger.info(
        "proposal.targeting_patched",
        proposal_id=proposal_id,
        location=body.location_targeting,
        user_id=user_id,
    )
    return EditResponse(proposal_id=proposal_id)


@router.patch("/{proposal_id}/keywords", response_model=EditResponse)
async def patch_keywords(
    proposal_id: str,
    body: PatchKeywordsRequest,
    user_id: CurrentUser,
) -> EditResponse:
    """Replace all keywords in a specific ad group (by index)."""
    try:
        uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal ID") from None

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            proposal, repo = await _load_proposal(session, proposal_id, user_id)

            if body.ad_group_index >= len(proposal.ad_groups):
                raise HTTPException(status_code=400, detail="ad_group_index out of range")

            from adcopilot.domain.launch.entities import KeywordProposal, MatchType

            new_keywords = [
                KeywordProposal(
                    text=kw["text"],
                    match_type=MatchType(kw.get("match_type", "BROAD")),
                    estimated_cpc_micros=int(kw.get("estimated_cpc_micros", 0)),
                )
                for kw in body.keywords
            ]

            from dataclasses import replace as dc_replace
            groups = list(proposal.ad_groups)
            old_group = groups[body.ad_group_index]
            groups[body.ad_group_index] = dc_replace(old_group, keywords=new_keywords)
            updated = dc_replace(proposal, ad_groups=groups)
            await repo.save(updated)
    finally:
        await engine.dispose()

    logger.info(
        "proposal.keywords_patched",
        proposal_id=proposal_id,
        ad_group_index=body.ad_group_index,
        keyword_count=len(body.keywords),
        user_id=user_id,
    )
    return EditResponse(proposal_id=proposal_id)


@router.patch("/{proposal_id}/ads", response_model=EditResponse)
async def patch_ads(
    proposal_id: str,
    body: PatchAdsRequest,
    user_id: CurrentUser,
) -> EditResponse:
    """Replace headlines and descriptions for the first ad in an ad group."""
    try:
        uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal ID") from None

    if len(body.headlines) < 3:
        raise HTTPException(status_code=422, detail="At least 3 headlines are required")
    if len(body.descriptions) < 2:
        raise HTTPException(status_code=422, detail="At least 2 descriptions are required")

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            proposal, repo = await _load_proposal(session, proposal_id, user_id)

            if body.ad_group_index >= len(proposal.ad_groups):
                raise HTTPException(status_code=400, detail="ad_group_index out of range")

            from adcopilot.domain.launch.entities import AdProposal

            groups = list(proposal.ad_groups)
            old_group = groups[body.ad_group_index]

            if not old_group.ads:
                raise HTTPException(status_code=400, detail="Ad group has no ads to edit")

            old_ad = old_group.ads[0]
            new_ad = AdProposal(
                headlines=body.headlines[:15],
                descriptions=body.descriptions[:4],
                final_url=old_ad.final_url,
                path_segments=old_ad.path_segments,
            )
            from dataclasses import replace as dc_replace
            new_ads = [new_ad] + list(old_group.ads[1:])
            groups[body.ad_group_index] = dc_replace(old_group, ads=new_ads)
            updated = dc_replace(proposal, ad_groups=groups)
            await repo.save(updated)
    finally:
        await engine.dispose()

    logger.info(
        "proposal.ads_patched",
        proposal_id=proposal_id,
        ad_group_index=body.ad_group_index,
        user_id=user_id,
    )
    return EditResponse(proposal_id=proposal_id)


@router.post("/{proposal_id}/regenerate-copy", response_model=EditResponse)
async def regenerate_copy(
    proposal_id: str,
    body: RegenerateCopyRequest,
    user_id: CurrentUser,
) -> EditResponse:
    """Re-generate ad copy for a specific ad group using the LLM.

    Triggers a background Celery task and returns immediately.
    The client should poll GET /app/launch/preview/{proposal_id} to see the update.
    """
    try:
        uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal ID") from None

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            proposal, _ = await _load_proposal(session, proposal_id, user_id)

            if body.ad_group_index >= len(proposal.ad_groups):
                raise HTTPException(status_code=400, detail="ad_group_index out of range")

            brief_id = str(proposal.brief_id)
    finally:
        await engine.dispose()

    from adcopilot.interfaces.worker.tasks import regenerate_ad_copy_task

    regenerate_ad_copy_task.delay(
        brief_id=brief_id,
        proposal_id=proposal_id,
        ad_group_index=body.ad_group_index,
    )

    logger.info(
        "proposal.regenerate_copy_queued",
        proposal_id=proposal_id,
        ad_group_index=body.ad_group_index,
        user_id=user_id,
    )
    return EditResponse(proposal_id=proposal_id, status="regenerating")
