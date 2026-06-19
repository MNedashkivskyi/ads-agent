"""Campaign Intelligence Engine — keyword API.

POST /api/campaigns/{id}/keywords/generate   → 202 + run_id (status: generating)
POST /api/campaigns/{id}/keywords/validate    → 202 + run_id (status: validating)
GET  /api/campaigns/{id}/keywords/status       → pollable status
GET  /api/campaigns/{id}/keywords/comparison   → brand-vs-intent proof view

The flow is provided behind ``get_keyword_flow`` so tests can swap an in-memory
implementation for the DB + Celery one.
"""

from __future__ import annotations

from typing import Annotated, Protocol

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from adcopilot.application.entitlements import Capability
from adcopilot.config import get_settings
from adcopilot.domain.campaign_intelligence.keywords.keyword_comparison import KeywordComparison
from adcopilot.infrastructure.cie.keyword_flow import (
    CampaignForbidden,
    CampaignNotFound,
    DbKeywordFlowService,
)
from adcopilot.interfaces.api.account_access import assert_campaign_access
from adcopilot.interfaces.api.auth_middleware import CurrentUser
from adcopilot.interfaces.api.deps import require_capability

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["cie-keywords"])


# ---------------------------------------------------------------------------
# Flow facade (swappable for tests)
# ---------------------------------------------------------------------------


class KeywordFlowService(Protocol):
    async def generate(
        self,
        *,
        campaign_id: str,
        user_id: str,
        account_id: str | None = None,
        vertical: str | None = None,
        language: str | None = None,
        service: str | None = None,
        problems: list[str] | None = None,
        seeds: list[str] | None = None,
    ) -> str: ...

    async def validate(self, *, campaign_id: str, user_id: str) -> str: ...

    async def get_status(
        self, *, campaign_id: str, user_id: str
    ) -> tuple[str | None, str | None]: ...

    async def comparison(self, *, campaign_id: str, user_id: str) -> KeywordComparison | None: ...

    async def analyze(
        self,
        *,
        campaign_id: str,
        user_id: str,
        account_id: str | None = None,
        vertical: str | None = None,
        language: str | None = None,
        service: str | None = None,
        problems: list[str] | None = None,
    ) -> KeywordComparison: ...

    async def get_harvest(self, *, campaign_id: str, user_id: str) -> dict | None: ...

    async def trigger_harvest(self, *, campaign_id: str, user_id: str) -> str: ...

    async def adopt_proposal(
        self, *, campaign_id: str, user_id: str, term: str, kind: str, decision: str
    ) -> bool: ...


def get_keyword_flow() -> KeywordFlowService:
    return DbKeywordFlowService(get_settings())


FlowDep = Annotated[KeywordFlowService, Depends(get_keyword_flow)]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class GenerateKeywordsRequest(BaseModel):
    account_id: str | None = None
    vertical: str | None = None
    language: str | None = None
    service: str | None = None
    problems: list[str] = Field(default_factory=list)
    seeds: list[str] = Field(default_factory=list)


class RunResponse(BaseModel):
    run_id: str
    status: str


class StatusResponse(BaseModel):
    status: str  # generating | generated | validating | ready | failed | none
    run_id: str | None = None


class RankedKeywordResponse(BaseModel):
    phrase: str
    intent: str
    monthly_searches: int
    score: float
    competition: str


class IntentGroupResponse(BaseModel):
    intent: str
    keyword_count: int
    total_monthly_volume: int
    avg_score: float
    top_keywords: list[RankedKeywordResponse]
    rationale: str = ""


class ComparisonResponse(BaseModel):
    groups: list[IntentGroupResponse]
    brand_total_volume: int
    intent_total_volume: int
    verdict: str
    multiplier: float


def _map_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, CampaignForbidden):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, CampaignNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/campaigns/{campaign_id}/keywords/generate",
    response_model=RunResponse,
    status_code=202,
)
async def generate_keywords(
    campaign_id: str,
    body: GenerateKeywordsRequest,
    user_id: CurrentUser,
    flow: FlowDep,
    _cap: Annotated[None, Depends(require_capability(Capability.ADVANCED_OPTIMIZATION))] = None,
) -> RunResponse:
    try:
        run_id = await flow.generate(
            campaign_id=campaign_id,
            user_id=user_id,
            account_id=body.account_id,
            vertical=body.vertical,
            language=body.language,
            service=body.service,
            problems=body.problems,
            seeds=body.seeds,
        )
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    return RunResponse(run_id=run_id, status="generating")


@router.post(
    "/campaigns/{campaign_id}/keywords/analyze",
    response_model=ComparisonResponse,
)
async def analyze_keywords(
    campaign_id: str,
    body: GenerateKeywordsRequest,
    user_id: CurrentUser,
    flow: FlowDep,
    _cap: Annotated[None, Depends(require_capability(Capability.ADVANCED_OPTIMIZATION))] = None,
) -> ComparisonResponse:
    """Synchronous: generate → validate → rank, returning the brand-vs-intent
    comparison in one call. AI-generation-heavy, so gated behind
    advanced_optimization (Professional and above)."""
    from adcopilot.domain.exceptions import AdCopilotError

    try:
        comparison = await flow.analyze(
            campaign_id=campaign_id,
            user_id=user_id,
            account_id=body.account_id,
            vertical=body.vertical,
            language=body.language,
            service=body.service,
            problems=body.problems,
        )
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    except AdCopilotError as exc:
        # LLM / volume failures surface as a clean 502 instead of an endless spinner.
        raise HTTPException(
            status_code=502,
            detail="Nie udało się przeanalizować słów kluczowych. Spróbuj ponownie.",
        ) from exc
    return _to_response(comparison)


@router.post(
    "/campaigns/{campaign_id}/keywords/validate",
    response_model=RunResponse,
    status_code=202,
)
async def validate_keywords(
    campaign_id: str,
    user_id: CurrentUser,
    flow: FlowDep,
    _cap: Annotated[None, Depends(require_capability(Capability.ADVANCED_OPTIMIZATION))] = None,
) -> RunResponse:
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    try:
        run_id = await flow.validate(campaign_id=campaign_id, user_id=user_id)
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    return RunResponse(run_id=run_id, status="validating")


@router.get("/campaigns/{campaign_id}/keywords/status", response_model=StatusResponse)
async def keyword_status(
    campaign_id: str,
    user_id: CurrentUser,
    flow: FlowDep,
) -> StatusResponse:
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    status, run_id = await flow.get_status(campaign_id=campaign_id, user_id=user_id)
    return StatusResponse(status=status or "none", run_id=run_id)


@router.get("/campaigns/{campaign_id}/keywords/comparison", response_model=ComparisonResponse)
async def keyword_comparison(
    campaign_id: str,
    user_id: CurrentUser,
    flow: FlowDep,
) -> ComparisonResponse:
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    comparison = await flow.comparison(campaign_id=campaign_id, user_id=user_id)
    if comparison is None:
        raise HTTPException(status_code=404, detail="No keyword run found")
    return _to_response(comparison)


class HarvestProposalResponse(BaseModel):
    term: str
    kind: str
    impressions: int
    clicks: int
    conversions: float
    cost_micros: int
    ctr: float
    intent: str | None = None


class HarvestResponse(BaseModel):
    promotions: list[HarvestProposalResponse]
    negatives: list[HarvestProposalResponse]


class AdoptProposalRequest(BaseModel):
    term: str
    kind: str  # promote | negative
    decision: str = "adopt"  # adopt | dismiss


@router.get("/campaigns/{campaign_id}/keywords/harvest", response_model=HarvestResponse)
async def keyword_harvest(campaign_id: str, user_id: CurrentUser, flow: FlowDep) -> HarvestResponse:
    """Surface harvested promotion + negative proposals for one-click adoption."""
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    data = await flow.get_harvest(campaign_id=campaign_id, user_id=user_id)
    if data is None:
        return HarvestResponse(promotions=[], negatives=[])
    return HarvestResponse(
        promotions=[HarvestProposalResponse(**p.__dict__) for p in data["promotions"]],
        negatives=[HarvestProposalResponse(**p.__dict__) for p in data["negatives"]],
    )


@router.post(
    "/campaigns/{campaign_id}/keywords/harvest/run", response_model=RunResponse, status_code=202
)
async def run_harvest(campaign_id: str, user_id: CurrentUser, flow: FlowDep) -> RunResponse:
    """Trigger a search-term harvest for the campaign's account on demand."""
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    try:
        account_id = await flow.trigger_harvest(campaign_id=campaign_id, user_id=user_id)
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    return RunResponse(run_id=account_id, status="harvesting")


@router.post("/campaigns/{campaign_id}/keywords/harvest/adopt")
async def adopt_harvest(
    campaign_id: str, body: AdoptProposalRequest, user_id: CurrentUser, flow: FlowDep
) -> dict:
    """Adopt or dismiss a harvested proposal."""
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    try:
        updated = await flow.adopt_proposal(
            campaign_id=campaign_id,
            user_id=user_id,
            term=body.term,
            kind=body.kind,
            decision=body.decision,
        )
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    return {"updated": updated}


def _to_response(c: KeywordComparison) -> ComparisonResponse:
    return ComparisonResponse(
        groups=[
            IntentGroupResponse(
                intent=g.intent,
                keyword_count=g.keyword_count,
                total_monthly_volume=g.total_monthly_volume,
                avg_score=g.avg_score,
                rationale=g.rationale,
                top_keywords=[
                    RankedKeywordResponse(
                        phrase=k.phrase,
                        intent=k.intent,
                        monthly_searches=k.monthly_searches,
                        score=k.score,
                        competition=k.competition,
                    )
                    for k in g.top_keywords
                ],
            )
            for g in c.groups
        ],
        brand_total_volume=c.brand_total_volume,
        intent_total_volume=c.intent_total_volume,
        verdict=c.verdict,
        multiplier=c.multiplier,
    )
