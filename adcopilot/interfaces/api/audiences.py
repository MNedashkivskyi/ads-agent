"""Audience management API — customer match upload and audience performance."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["audiences"])


class UploadCustomerListResponse(BaseModel):
    user_list_resource_name: str
    uploaded_count: int
    list_name: str


class AudiencePerformanceItem(BaseModel):
    criterion_id: int
    campaign_id: int
    ad_group_id: int
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float
    ctr: float
    conv_rate: float


class AudiencesResponse(BaseModel):
    audiences: list[AudiencePerformanceItem]


@router.post("/{user_id}/audiences/upload-customer-list", response_model=UploadCustomerListResponse)
async def upload_customer_list(
    user_id: str,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    list_name: str = Form(...),
    email_column: str = Form(default="email"),
) -> UploadCustomerListResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.upload_customer_list import upload_customer_list as uc
    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter

    settings = get_settings()
    csv_bytes = await file.read()

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)

            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            account = accounts[0]
            credentials = await credentials_repo.get(AccountId(account.id))
            if credentials is None:
                raise HTTPException(status_code=422, detail="Google Ads account not connected")

        mutations = GoogleAdsMutationsAdapter(settings)
        result = await uc(
            refresh_token=credentials.refresh_token,
            customer_id=account.customer_id,
            list_name=list_name,
            csv_bytes=csv_bytes,
            mutations_adapter=mutations,
            email_column=email_column,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        await engine.dispose()

    return UploadCustomerListResponse(
        user_list_resource_name=result.user_list_resource_name,
        uploaded_count=result.uploaded_count,
        list_name=result.list_name,
    )


@router.get("/{user_id}/audiences", response_model=AudiencesResponse)
async def list_audiences(
    user_id: str,
    current_user: CurrentUser,
) -> AudiencesResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.entities import UserId
    from adcopilot.infrastructure.db.models import AudiencePerformanceSnapshotModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            import uuid
            account_uuid = uuid.UUID(accounts[0].id)
            result = await session.execute(
                select(AudiencePerformanceSnapshotModel)
                .where(AudiencePerformanceSnapshotModel.account_id == account_uuid)
                .order_by(AudiencePerformanceSnapshotModel.snapshot_date.desc())
                .limit(200)
            )
            rows = list(result.scalars().all())
    finally:
        await engine.dispose()

    items = [
        AudiencePerformanceItem(
            criterion_id=r.criterion_id,
            campaign_id=r.campaign_id,
            ad_group_id=r.ad_group_id,
            impressions=r.impressions,
            clicks=r.clicks,
            cost_micros=r.cost_micros,
            conversions=r.conversions,
            ctr=r.clicks / r.impressions if r.impressions else 0.0,
            conv_rate=r.conversions / r.clicks if r.clicks else 0.0,
        )
        for r in rows
    ]
    return AudiencesResponse(audiences=items)
