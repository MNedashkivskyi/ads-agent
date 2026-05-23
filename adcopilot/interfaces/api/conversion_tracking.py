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
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )
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


# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------


class GuideStepResponse(BaseModel):
    step: int
    title: str
    description: str
    is_verify: bool


class PlatformDetectionResponse(BaseModel):
    platform: str
    platform_label: str
    steps: list[GuideStepResponse]
    gtm_container_hint: str | None = None


@router.get(
    "/{user_id}/conversion-tracking/platform",
    response_model=PlatformDetectionResponse,
)
async def get_platform_detection(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PlatformDetectionResponse:
    """Detect website platform and return matching installation guide."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy import desc, select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.detect_website_platform import (
        detect_platform_from_final_urls,
    )
    from adcopilot.domain.conversion_tracking.installation_guides import get_guide
    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.models import AdSnapshotModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            account = accounts[0]
            import uuid

            acct_uuid = uuid.UUID(str(account.id))

            stmt = (
                select(AdSnapshotModel.final_urls_json)
                .where(
                    AdSnapshotModel.account_id == acct_uuid,
                    AdSnapshotModel.final_urls_json.isnot(None),
                )
                .order_by(desc(AdSnapshotModel.snapshot_date))
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
    finally:
        await engine.dispose()

    final_urls_json = row or "[]"
    platform = await detect_platform_from_final_urls(final_urls_json)
    guide = get_guide(platform)

    return PlatformDetectionResponse(
        platform=guide.platform,
        platform_label=guide.platform_label,
        steps=[
            GuideStepResponse(
                step=s.step,
                title=s.title,
                description=s.description,
                is_verify=s.is_verify,
            )
            for s in guide.steps
        ],
        gtm_container_hint=guide.gtm_container_hint,
    )


# ---------------------------------------------------------------------------
# Tracking validation
# ---------------------------------------------------------------------------


class ValidationActionDetail(BaseModel):
    name: str
    status: str
    all_conversions: float


class TrackingValidationResponse(BaseModel):
    status: str
    message_pl: str
    failing_actions: list[ValidationActionDetail]


@router.post(
    "/{user_id}/conversion-tracking/validate",
    response_model=TrackingValidationResponse,
)
async def validate_conversion_tracking(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> TrackingValidationResponse:
    """Validate conversion tracking is receiving data."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.validate_conversion_tracking import (
        ValidateConversionTrackingUseCase,
    )
    from adcopilot.domain.entities import AccountId, UserId
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
            use_case = ValidateConversionTrackingUseCase(google_ads=google_ads)
            result = await use_case.execute(
                refresh_token=credentials.refresh_token,
                customer_id=account.customer_id,
            )
    finally:
        await engine.dispose()

    return TrackingValidationResponse(
        status=result.status,
        message_pl=result.message_pl,
        failing_actions=[ValidationActionDetail(**a) for a in result.failing_actions],
    )


# ---------------------------------------------------------------------------
# GTM Container download
# ---------------------------------------------------------------------------


class GTMContainerResponse(BaseModel):
    platform: str
    filename: str
    container: dict


@router.get(
    "/{user_id}/conversion-tracking/gtm-container",
    response_model=GTMContainerResponse,
)
async def get_gtm_container(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    conversion_id: str = "",
    conversion_label: str = "",
) -> GTMContainerResponse:
    """Generate and return a GTM container JSON for the user's detected platform."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.detect_website_platform import (
        detect_platform_from_final_urls,
    )
    from adcopilot.application.use_cases.generate_gtm_container import generate_gtm_container
    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.models import KeywordSnapshotModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No accounts found")
            account = accounts[0]

            stmt = (
                select(KeywordSnapshotModel.final_urls)
                .where(KeywordSnapshotModel.account_id == account.id)
                .order_by(text("snapshot_date DESC"))
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
    finally:
        await engine.dispose()

    final_urls_json = row or "[]"
    platform = await detect_platform_from_final_urls(final_urls_json)
    container = generate_gtm_container(
        conversion_id=conversion_id or "AW-XXXXXXXXX/YYYYYYYYYYYYYYY",
        conversion_label=conversion_label or "YYYYYYYYYYYYYYY",
        platform=platform,
    )
    return GTMContainerResponse(
        platform=platform,
        filename=f"adswise_gtm_{platform}.json",
        container=container,
    )


# ---------------------------------------------------------------------------
# Implementation partner marketplace
# ---------------------------------------------------------------------------


class PartnerResponse(BaseModel):
    id: str
    name: str
    email: str
    website: str | None
    city: str
    voivodeship: str
    platforms_supported: list[str]
    fixed_price_pln: int
    avg_turnaround_hours: int
    rating: float
    completed_jobs: int


class RequestImplementationBody(BaseModel):
    partner_id: str | None = None
    auto_match: bool = True


class ImplementationRequestResponse(BaseModel):
    id: str
    client_id: str
    partner_id: str
    account_id: str
    status: str
    platform: str
    created_at: str


class ImplementationStatusResponse(BaseModel):
    has_active_request: bool
    request: ImplementationRequestResponse | None


@router.get(
    "/{user_id}/conversion-tracking/partners",
    response_model=list[PartnerResponse],
)
async def list_implementation_partners(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    platform: str = "",
) -> list[PartnerResponse]:
    """List active implementation partners, optionally filtered by platform."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.models import ImplementationPartnerModel

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            stmt = (
                select(ImplementationPartnerModel)
                .where(
                    ImplementationPartnerModel.is_active == True  # noqa: E712
                )
                .order_by(ImplementationPartnerModel.rating.desc())
            )
            result = await session.execute(stmt)
            partners = list(result.scalars().all())
    finally:
        await engine.dispose()

    if platform:
        partners = [p for p in partners if platform in (p.platforms_supported or [])]

    return [
        PartnerResponse(
            id=str(p.id),
            name=p.name,
            email=p.email,
            website=p.website,
            city=p.city,
            voivodeship=p.voivodeship,
            platforms_supported=p.platforms_supported or [],
            fixed_price_pln=p.fixed_price_pln,
            avg_turnaround_hours=p.avg_turnaround_hours,
            rating=p.rating,
            completed_jobs=p.completed_jobs,
        )
        for p in partners
    ]


@router.post(
    "/{user_id}/conversion-tracking/request-implementation",
    response_model=ImplementationRequestResponse,
)
async def request_implementation_endpoint(
    user_id: str,
    body: RequestImplementationBody,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImplementationRequestResponse:
    """Create an implementation request and notify the partner."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy import select, text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.detect_website_platform import (
        detect_platform_from_final_urls,
    )
    from adcopilot.application.use_cases.request_implementation import request_implementation
    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.models import KeywordSnapshotModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No accounts found")
            account = accounts[0]

            stmt = (
                select(KeywordSnapshotModel.final_urls)
                .where(KeywordSnapshotModel.account_id == account.id)
                .order_by(text("snapshot_date DESC"))
                .limit(1)
            )
            row = (await session.execute(stmt)).scalar_one_or_none()
            platform = await detect_platform_from_final_urls(row or "[]")

            try:
                req = await request_implementation(
                    user_id=user_id,
                    account_id=str(account.id),
                    platform=platform,
                    session=session,
                    partner_id=body.partner_id,
                )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            await session.commit()
    finally:
        await engine.dispose()

    return ImplementationRequestResponse(
        id=req.id,
        client_id=req.client_id,
        partner_id=req.partner_id,
        account_id=req.account_id,
        status=req.status.value,
        platform=req.platform,
        created_at=req.created_at.isoformat(),
    )


@router.get(
    "/{user_id}/conversion-tracking/implementation-status",
    response_model=ImplementationStatusResponse,
)
async def get_implementation_status(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ImplementationStatusResponse:
    """Check if the user has an active implementation request."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.models import ImplementationRequestModel

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(ImplementationRequestModel)
                .where(ImplementationRequestModel.client_id == user_id)
                .where(ImplementationRequestModel.status.in_(["requested", "accepted"]))
                .order_by(ImplementationRequestModel.created_at.desc())
                .limit(1)
            )
            req = result.scalar_one_or_none()
    finally:
        await engine.dispose()

    if not req:
        return ImplementationStatusResponse(has_active_request=False, request=None)

    return ImplementationStatusResponse(
        has_active_request=True,
        request=ImplementationRequestResponse(
            id=str(req.id),
            client_id=req.client_id,
            partner_id=str(req.partner_id),
            account_id=str(req.account_id),
            status=req.status,
            platform=req.platform,
            created_at=req.created_at.isoformat(),
        ),
    )
