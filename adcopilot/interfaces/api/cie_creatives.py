"""Campaign Intelligence Engine — creative (hook) API.

POST /api/campaigns/{id}/creatives/generate  → 202 + run_id (generating)
POST /api/campaigns/{id}/creatives/select      → 202 (judge + select)
POST /api/campaigns/{id}/creatives/finalize     → 202 (assemble RSA + tag assets)
GET  /api/campaigns/{id}/creatives/status        → status + RSA payload when ready
"""

from __future__ import annotations

from typing import Annotated, Protocol

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from adcopilot.config import get_settings
from adcopilot.infrastructure.cie.creative_flow import (
    CampaignForbidden,
    CampaignNotFound,
    DbCreativeFlowService,
)
from adcopilot.interfaces.api.account_access import assert_campaign_access
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["cie-creatives"])


class CreativeFlowService(Protocol):
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
    ) -> str: ...

    async def select(self, *, campaign_id: str, user_id: str) -> str: ...

    async def finalize(self, *, campaign_id: str, user_id: str) -> str: ...

    async def get_status(
        self, *, campaign_id: str, user_id: str
    ) -> tuple[str | None, str | None, dict | None]: ...


def get_creative_flow() -> CreativeFlowService:
    return DbCreativeFlowService(get_settings())


FlowDep = Annotated[CreativeFlowService, Depends(get_creative_flow)]


class GenerateCreativesRequest(BaseModel):
    account_id: str | None = None
    vertical: str | None = None
    language: str | None = None
    service: str | None = None
    problems: list[str] = Field(default_factory=list)


class RunResponse(BaseModel):
    run_id: str
    status: str


class CreativeStatusResponse(BaseModel):
    status: str
    run_id: str | None = None
    rsa_payload: dict | None = None


def _map_exc(exc: Exception) -> HTTPException:
    if isinstance(exc, CampaignForbidden):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, CampaignNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/campaigns/{campaign_id}/creatives/generate", response_model=RunResponse, status_code=202
)
async def generate_creatives(
    campaign_id: str,
    body: GenerateCreativesRequest,
    user_id: CurrentUser,
    flow: FlowDep,
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
        )
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    return RunResponse(run_id=run_id, status="generating")


@router.post(
    "/campaigns/{campaign_id}/creatives/select", response_model=RunResponse, status_code=202
)
async def select_creatives(campaign_id: str, user_id: CurrentUser, flow: FlowDep) -> RunResponse:
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    try:
        run_id = await flow.select(campaign_id=campaign_id, user_id=user_id)
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    return RunResponse(run_id=run_id, status="selecting")


@router.post(
    "/campaigns/{campaign_id}/creatives/finalize", response_model=RunResponse, status_code=202
)
async def finalize_creatives(campaign_id: str, user_id: CurrentUser, flow: FlowDep) -> RunResponse:
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    try:
        run_id = await flow.finalize(campaign_id=campaign_id, user_id=user_id)
    except (CampaignNotFound, CampaignForbidden, ValueError) as exc:
        raise _map_exc(exc) from exc
    return RunResponse(run_id=run_id, status="finalizing")


@router.get("/campaigns/{campaign_id}/creatives/status", response_model=CreativeStatusResponse)
async def creative_status(
    campaign_id: str, user_id: CurrentUser, flow: FlowDep
) -> CreativeStatusResponse:
    await assert_campaign_access(get_settings(), campaign_id, user_id)
    status, run_id, payload = await flow.get_status(campaign_id=campaign_id, user_id=user_id)
    return CreativeStatusResponse(status=status or "none", run_id=run_id, rsa_payload=payload)
