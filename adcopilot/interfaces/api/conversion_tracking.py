"""Conversion tracking audit API endpoints."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["conversion-tracking"])


class ConversionActionStatusResponse(BaseModel):
    action_id: int
    name: str
    status: str
    all_conversions: float
    health: str


class ConversionAuditResponse(BaseModel):
    account_id: str
    action_statuses: list[ConversionActionStatusResponse]
    diagnostic_message_pl: str
    overall_health: str


@router.get(
    "/{user_id}/conversion-tracking/audit",
    response_model=ConversionAuditResponse,
)
async def get_conversion_audit(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConversionAuditResponse:
    """Run ConversionTrackingAuditUseCase and return the result."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return await _run_audit(user_id, settings)


@router.post(
    "/{user_id}/conversion-tracking/revalidate",
    response_model=ConversionAuditResponse,
)
async def revalidate_conversion_audit(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ConversionAuditResponse:
    """Re-run the conversion tracking audit with fresh data."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    return await _run_audit(user_id, settings)


async def _run_audit(user_id: str, settings: Settings) -> ConversionAuditResponse:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.audit_conversion_tracking import (
        ConversionTrackingAuditUseCase,
    )
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )
    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            prompt_repo = SqlPromptVersionRepository(session)

            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            # Use the first connected account
            account = accounts[0]
            credentials = await credentials_repo.get(AccountId(account.id))
            if credentials is None:
                raise HTTPException(status_code=422, detail="Google Ads account not connected")

            google_ads = GoogleAdsQueriesAdapter(settings)
            llm = AnthropicClient(api_key=settings.LLM_API_KEY)

            use_case = ConversionTrackingAuditUseCase(
                google_ads=google_ads,
                llm=llm,
                prompt_repo=prompt_repo,
            )
            result = await use_case.execute(
                refresh_token=credentials.refresh_token,
                customer_id=account.customer_id,
            )
    finally:
        await engine.dispose()

    return ConversionAuditResponse(
        account_id=result.account_id,
        action_statuses=[
            ConversionActionStatusResponse(
                action_id=s.action_id,
                name=s.name,
                status=s.status,
                all_conversions=s.all_conversions,
                health=s.health.value,
            )
            for s in result.action_statuses
        ],
        diagnostic_message_pl=result.diagnostic_message_pl,
        overall_health=result.overall_health.value,
    )
