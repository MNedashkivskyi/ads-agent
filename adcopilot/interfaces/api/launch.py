"""Campaign launch preview endpoint.

Provides a read-only JSON view of a CampaignProposal for the
/app/launch/preview/<proposal_id> web-app route.

Authentication is intentionally kept lightweight here — the proposal ID
is a UUID that is only known to the bot (sent via Telegram), so guessing
it is not a realistic attack vector.  A proper auth middleware (e.g.
session cookie check) should be added when the full web app is wired up.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import get_settings
from adcopilot.infrastructure.vertical_templates.yaml_adapter import YamlVerticalTemplateAdapter

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/app/launch", tags=["launch"])
api_router = APIRouter(prefix="/api", tags=["launch"])

_template_adapter = YamlVerticalTemplateAdapter()


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class KeywordResponse(BaseModel):
    text: str
    match_type: str
    estimated_cpc_pln: float


class AdResponse(BaseModel):
    headlines: list[str]
    descriptions: list[str]
    final_url: str
    path_segments: list[str]


class AdGroupResponse(BaseModel):
    name: str
    keywords: list[KeywordResponse]
    ads: list[AdResponse]


class ProposalPreviewResponse(BaseModel):
    proposal_id: str
    campaign_name: str
    daily_budget_pln: float
    location_targeting: str
    bidding_strategy: str
    ad_groups: list[AdGroupResponse]
    negative_keywords: list[str]
    estimated_cpc_min_pln: float
    estimated_cpc_max_pln: float
    generated_at: str


class VerticalResponse(BaseModel):
    id: str
    display_name: str
    emoji: str
    description: str
    common_services: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_MICROS_PER_PLN = 1_000_000


@api_router.get("/verticals", response_model=list[VerticalResponse])
async def list_verticals() -> list[VerticalResponse]:
    """Return all available vertical templates for the campaign creation wizard."""
    summaries = _template_adapter.list_verticals()
    result: list[VerticalResponse] = []
    for summary in summaries:
        tmpl = _template_adapter.get_template(summary.vertical_id)
        if tmpl is None:
            continue
        services_preview = tmpl.common_services[:3]
        description = ", ".join(services_preview) if services_preview else tmpl.display_name
        result.append(
            VerticalResponse(
                id=tmpl.vertical_id,
                display_name=tmpl.display_name,
                emoji=tmpl.display_emoji,
                description=description,
                common_services=tmpl.common_services,
            )
        )
    return result


@router.get("/preview/{proposal_id}", response_model=ProposalPreviewResponse)
async def get_proposal_preview(proposal_id: str) -> ProposalPreviewResponse:
    """Return a read-only view of a campaign proposal.

    Used by the /app/launch/preview/<proposal_id> web route so users can
    review the full proposal before launching.
    """
    try:
        uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal ID format") from None

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from adcopilot.domain.launch.entities import CampaignProposalId
            from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
                SqlCampaignProposalRepository,
            )

            repo = SqlCampaignProposalRepository(session)
            proposal = await repo.get(CampaignProposalId(proposal_id))
    finally:
        await engine.dispose()

    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    return ProposalPreviewResponse(
        proposal_id=str(proposal.id),
        campaign_name=proposal.campaign_name,
        daily_budget_pln=proposal.daily_budget_micros / _MICROS_PER_PLN,
        location_targeting=proposal.location_targeting,
        bidding_strategy=proposal.bidding_strategy,
        ad_groups=[
            AdGroupResponse(
                name=ag.name,
                keywords=[
                    KeywordResponse(
                        text=kw.text,
                        match_type=kw.match_type,
                        estimated_cpc_pln=kw.estimated_cpc_micros / _MICROS_PER_PLN,
                    )
                    for kw in ag.keywords
                ],
                ads=[
                    AdResponse(
                        headlines=ad.headlines,
                        descriptions=ad.descriptions,
                        final_url=ad.final_url,
                        path_segments=list(ad.path_segments),
                    )
                    for ad in ag.ads
                ],
            )
            for ag in proposal.ad_groups
        ],
        negative_keywords=proposal.negative_keywords,
        estimated_cpc_min_pln=proposal.estimated_cpc_range[0] / _MICROS_PER_PLN,
        estimated_cpc_max_pln=proposal.estimated_cpc_range[1] / _MICROS_PER_PLN,
        generated_at=proposal.generated_at.isoformat(),
    )
