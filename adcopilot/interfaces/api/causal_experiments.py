"""Causal experiments API — propose/list/inspect/promote native Google Ads experiments.

Distinct from the creative-rotation `experiments.py` (ad A/B): these are native
Google Ads campaign experiments (CampaignDraft + Experiment) used for causal
measurement of bidding/tCPA changes. Human-in-the-loop throughout: launched only on
an explicit propose call, promoted only on an explicit promote call.
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["causal-experiments"])

_VALID_CHANGE_KINDS = {"BIDDING_STRATEGY", "TARGET_CPA", "TARGET_ROAS"}


class ProposeExperimentRequest(BaseModel):
    base_campaign_id: int
    change_kind: str  # BIDDING_STRATEGY | TARGET_CPA | TARGET_ROAS
    change_payload: dict
    traffic_split: int = Field(default=50, ge=10, le=90)
    duration_days: int = Field(default=14, ge=7, le=90)
    source_recommendation_id: str | None = None


class CausalExperimentResponse(BaseModel):
    id: str
    base_campaign_id: int
    change_kind: str
    change_payload: dict
    traffic_split: int
    status: str
    verdict: str
    confidence: float | None
    started_at: str | None
    ends_at: str | None
    control_metrics: dict
    treatment_metrics: dict
    last_error: str | None
    source_recommendation_id: str | None
    created_at: str


def _to_response(e) -> CausalExperimentResponse:
    return CausalExperimentResponse(
        id=str(e.id),
        base_campaign_id=e.base_campaign_id,
        change_kind=e.change_kind.value,
        change_payload=e.change_payload,
        traffic_split=e.traffic_split,
        status=e.status.value,
        verdict=e.verdict.value,
        confidence=e.confidence,
        started_at=e.started_at.isoformat() if e.started_at else None,
        ends_at=e.ends_at.isoformat() if e.ends_at else None,
        control_metrics=e.control_metrics,
        treatment_metrics=e.treatment_metrics,
        last_error=e.last_error,
        source_recommendation_id=e.source_recommendation_id,
        created_at=e.created_at.isoformat() if e.created_at else "",
    )


def _imports():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.campaign_experiment_repository import (
        CampaignExperimentRepository,
    )
    from adcopilot.interfaces.api.measurement import _resolve_account

    return AsyncSession, create_async_engine, CampaignExperimentRepository, _resolve_account


@router.get("/{user_id}/causal-experiments", response_model=list[CausalExperimentResponse])
async def list_causal_experiments(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[CausalExperimentResponse]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    AsyncSession, create_async_engine, Repo, _resolve_account = _imports()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            experiments = await Repo(session).list_for_account(str(account.id))
            return [_to_response(e) for e in experiments]
    finally:
        await engine.dispose()


@router.get(
    "/{user_id}/causal-experiments/{experiment_id}", response_model=CausalExperimentResponse
)
async def get_causal_experiment(
    user_id: str,
    experiment_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CausalExperimentResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    AsyncSession, create_async_engine, Repo, _resolve_account = _imports()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            exp = await Repo(session).get(uuid.UUID(experiment_id))
            if exp is None or exp.account_id != str(account.id):
                raise HTTPException(status_code=404, detail="Eksperyment nie znaleziony")
            return _to_response(exp)
    finally:
        await engine.dispose()


@router.post("/{user_id}/causal-experiments/propose", response_model=CausalExperimentResponse)
async def propose_causal_experiment(
    user_id: str,
    body: ProposeExperimentRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CausalExperimentResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    if body.change_kind not in _VALID_CHANGE_KINDS:
        raise HTTPException(status_code=422, detail="Nieobsługiwany typ zmiany eksperymentu")

    AsyncSession, create_async_engine, Repo, _resolve_account = _imports()
    from adcopilot.application.use_cases.campaign_experiment_flow import (
        propose_bidding_experiment,
    )
    from adcopilot.domain.campaign_experiment import CampaignExperiment, ExperimentChangeKind
    from adcopilot.infrastructure.google_ads.experiment_mutations_adapter import (
        GoogleAdsExperimentAdapter,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, refresh_token = await _resolve_account(session, user_id)
            if not refresh_token:
                raise HTTPException(status_code=400, detail="Brak połączenia z Google Ads")
            experiment = CampaignExperiment(
                account_id=str(account.id),
                base_campaign_id=body.base_campaign_id,
                change_kind=ExperimentChangeKind(body.change_kind),
                change_payload=body.change_payload,
                traffic_split=body.traffic_split,
                source_recommendation_id=body.source_recommendation_id,
            )
            adapter = GoogleAdsExperimentAdapter(settings)
            experiment = await propose_bidding_experiment(
                experiment=experiment,
                adapter=adapter,
                refresh_token=refresh_token,
                customer_id=account.customer_id,
                duration_days=body.duration_days,
            )
            await Repo(session).save(experiment)
            return _to_response(experiment)
    finally:
        await engine.dispose()


@router.post(
    "/{user_id}/causal-experiments/{experiment_id}/promote",
    response_model=CausalExperimentResponse,
)
async def promote_causal_experiment(
    user_id: str,
    experiment_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CausalExperimentResponse:
    return await _outcome(user_id, experiment_id, current_user, settings, promote=True)


@router.post(
    "/{user_id}/causal-experiments/{experiment_id}/end",
    response_model=CausalExperimentResponse,
)
async def end_causal_experiment(
    user_id: str,
    experiment_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CausalExperimentResponse:
    return await _outcome(user_id, experiment_id, current_user, settings, promote=False)


async def _outcome(
    user_id: str, experiment_id: str, current_user: str, settings: Settings, *, promote: bool
) -> CausalExperimentResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    AsyncSession, create_async_engine, Repo, _resolve_account = _imports()
    from adcopilot.application.use_cases.campaign_experiment_flow import (
        promote_experiment_outcome,
    )
    from adcopilot.infrastructure.google_ads.experiment_mutations_adapter import (
        GoogleAdsExperimentAdapter,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, refresh_token = await _resolve_account(session, user_id)
            if not refresh_token:
                raise HTTPException(status_code=400, detail="Brak połączenia z Google Ads")
            repo = Repo(session)
            exp = await repo.get(uuid.UUID(experiment_id))
            if exp is None or exp.account_id != str(account.id):
                raise HTTPException(status_code=404, detail="Eksperyment nie znaleziony")
            adapter = GoogleAdsExperimentAdapter(settings)
            exp = await promote_experiment_outcome(
                experiment=exp,
                adapter=adapter,
                refresh_token=refresh_token,
                customer_id=account.customer_id,
                promote=promote,
            )
            await repo.save(exp)
            return _to_response(exp)
    finally:
        await engine.dispose()
