"""PMax campaign API endpoints — eligibility check, creation, activation, status."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["pmax"])


# ---------------------------------------------------------------------------
# Response / Request models
# ---------------------------------------------------------------------------

class MerchantCenterInfo(BaseModel):
    merchant_id: int
    account_name: str
    status: str


class PMaxEligibilityResponse(BaseModel):
    eligible: bool
    merchant_center: MerchantCenterInfo | None = None
    instructions_pl: str | None = None


class CreatePMaxRequest(BaseModel):
    account_id: str
    monthly_budget_pln: float = Field(..., gt=0, le=50000)
    product_focus: str = Field(default="all", max_length=200)
    campaign_name: str = Field(..., min_length=3, max_length=100)
    final_url: str = Field(..., min_length=10, max_length=500)


class CreatePMaxResponse(BaseModel):
    campaign_resource_name: str
    budget_resource_name: str
    asset_group_resource_names: list[str]
    status: str = "PAUSED"
    message_pl: str


class EnablePMaxResponse(BaseModel):
    campaign_resource_name: str
    status: str = "ENABLED"
    message_pl: str


class PMaxCampaignSummary(BaseModel):
    campaign_resource_name: str
    campaign_name: str
    status: str
    daily_budget_pln: float | None = None
    impressions: int | None = None
    clicks: int | None = None
    conversions: float | None = None
    cost_pln: float | None = None
    roas: float | None = None


class PMaxStatusResponse(BaseModel):
    campaigns: list[PMaxCampaignSummary]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NO_MC_INSTRUCTIONS = (
    "Twoje konto Google Ads nie ma powiązanego konta Google Merchant Center. "
    "Aby utworzyć kampanię Performance Max, wykonaj następujące kroki:\n"
    "1. Zaloguj się do Google Merchant Center (merchants.google.com).\n"
    "2. W ustawieniach wybierz 'Połączone konta' → 'Google Ads'.\n"
    "3. Kliknij 'Połącz konto' i wpisz Identyfikator klienta Google Ads.\n"
    "4. Zaakceptuj zaproszenie w Google Ads (Narzędzia → Połączone konta).\n"
    "5. Po zatwierdzeniu wróć tutaj i odśwież stronę."
)


async def _get_session_and_account(
    user_id: str, account_id: str, settings: Settings
):
    """Returns (session, engine, account, oauth_creds) or raises HTTPException."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    session = AsyncSession(engine)
    await session.begin()

    account_repo = SqlGoogleAdsAccountRepository(session)
    account = await account_repo.get(AccountId(account_id))
    if account is None or str(account.user_id) != user_id:
        await session.rollback()
        await session.close()
        await engine.dispose()
        raise HTTPException(status_code=404, detail="Konto Google Ads nie zostało znalezione")

    oauth_repo = SqlOAuthCredentialsRepository(session, encryption_key=settings.TOKEN_ENCRYPTION_KEY)
    creds = await oauth_repo.get(AccountId(account_id))
    if creds is None:
        await session.rollback()
        await session.close()
        await engine.dispose()
        raise HTTPException(status_code=400, detail="Brak autoryzacji Google Ads dla tego konta")

    return session, engine, account, creds


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/{user_id}/pmax/eligibility", response_model=PMaxEligibilityResponse)
async def get_pmax_eligibility(
    user_id: str,
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PMaxEligibilityResponse:
    """Check if the account has a Merchant Center link and is eligible for PMax."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    session, engine, account, creds = await _get_session_and_account(user_id, account_id, settings)
    try:
        from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

        adapter = GoogleAdsQueriesAdapter(settings)
        mc_link = await adapter.get_merchant_center_link(
            refresh_token=creds.refresh_token,
            customer_id=account.customer_id,
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()

    if mc_link is None:
        return PMaxEligibilityResponse(
            eligible=False,
            merchant_center=None,
            instructions_pl=_NO_MC_INSTRUCTIONS,
        )

    return PMaxEligibilityResponse(
        eligible=True,
        merchant_center=MerchantCenterInfo(
            merchant_id=mc_link.merchant_id,
            account_name=mc_link.account_name,
            status=mc_link.status,
        ),
    )


@router.post("/{user_id}/pmax/create", response_model=CreatePMaxResponse)
async def create_pmax_campaign(
    user_id: str,
    body: CreatePMaxRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> CreatePMaxResponse:
    """Create a PAUSED Performance Max campaign (CCR-4: checks write_enabled + plan tier)."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    session, engine, account, creds = await _get_session_and_account(
        user_id, body.account_id, settings
    )
    try:
        # CCR-4: validate write_enabled and plan tier
        if not account.write_enabled:
            raise HTTPException(
                status_code=403,
                detail="Konto nie ma włączonego trybu zapisu. Skontaktuj się z pomocą techniczną.",
            )

        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
            SqlPromptVersionRepository,
        )
        from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
        from adcopilot.domain.entities import UserId, PlanTier

        user_repo = SqlUserRepository(session)
        user = await user_repo.get(UserId(user_id))
        if user is None or user.plan == PlanTier.STARTER:
            raise HTTPException(
                status_code=403,
                detail="Kampanie PMax są dostępne od planu Growth. Zaktualizuj swój plan.",
            )

        from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

        adapter = GoogleAdsQueriesAdapter(settings)
        mc_link = await adapter.get_merchant_center_link(
            refresh_token=creds.refresh_token,
            customer_id=account.customer_id,
        )
        if mc_link is None:
            raise HTTPException(
                status_code=400,
                detail="Brak powiązanego konta Merchant Center. Najpierw połącz Merchant Center.",
            )

        prompt_repo = SqlPromptVersionRepository(session)
        from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
        from adcopilot.infrastructure.google_ads.pmax_writer import PMaxCampaignWriter
        from adcopilot.application.use_cases.create_pmax_campaign import (
            CreatePMaxCampaignInput,
            CreatePMaxCampaignUseCase,
        )

        llm = AnthropicClient(api_key=settings.LLM_API_KEY)
        pmax_writer = PMaxCampaignWriter(settings)
        use_case = CreatePMaxCampaignUseCase(llm=llm, prompt_repo=prompt_repo, pmax_writer=pmax_writer)

        result = await use_case.execute(
            CreatePMaxCampaignInput(
                customer_id=account.customer_id,
                refresh_token=creds.refresh_token,
                merchant_center_link=mc_link,
                monthly_budget_pln=body.monthly_budget_pln,
                product_focus=body.product_focus,
                campaign_name=body.campaign_name,
                final_url=body.final_url,
                vertical="ecommerce",
            )
        )

        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as exc:
        await session.rollback()
        logger.error("pmax.create.error", user_id=user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Błąd podczas tworzenia kampanii PMax.")
    finally:
        await session.close()
        await engine.dispose()

    return CreatePMaxResponse(
        campaign_resource_name=result.campaign_resource_name,
        budget_resource_name=result.budget_resource_name,
        asset_group_resource_names=result.asset_group_resource_names,
        status="PAUSED",
        message_pl=f"Kampania '{body.campaign_name}' została utworzona i jest wstrzymana. Kliknij 'Aktywuj', aby ją uruchomić.",
    )


@router.post("/{user_id}/pmax/{campaign_resource_name:path}/enable", response_model=EnablePMaxResponse)
async def enable_pmax_campaign(
    user_id: str,
    campaign_resource_name: str,
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> EnablePMaxResponse:
    """Activate a PAUSED PMax campaign."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    session, engine, account, creds = await _get_session_and_account(user_id, account_id, settings)
    try:
        if not account.write_enabled:
            raise HTTPException(status_code=403, detail="Konto nie ma włączonego trybu zapisu.")

        from adcopilot.infrastructure.google_ads.pmax_writer import PMaxCampaignWriter

        writer = PMaxCampaignWriter(settings)
        await writer.enable_pmax_campaign(
            customer_id=account.customer_id,
            refresh_token=creds.refresh_token,
            campaign_resource_name=campaign_resource_name,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("pmax.enable.error", user_id=user_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Błąd podczas aktywacji kampanii PMax.")
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()

    return EnablePMaxResponse(
        campaign_resource_name=campaign_resource_name,
        status="ENABLED",
        message_pl="Kampania PMax została aktywowana.",
    )


@router.get("/{user_id}/pmax/status", response_model=PMaxStatusResponse)
async def get_pmax_status(
    user_id: str,
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> PMaxStatusResponse:
    """Return PMax campaigns with performance summary from the latest snapshot."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    session, engine, account, creds = await _get_session_and_account(user_id, account_id, settings)
    try:
        import datetime as _dt
        from adcopilot.domain.entities import AccountId
        from adcopilot.infrastructure.db.repositories.snapshot_repository import (
            SqlSnapshotRepository,
        )

        snapshot_repo = SqlSnapshotRepository(session)
        today = _dt.date.today()
        # Try today, fallback to yesterday if no data yet
        snapshots = await snapshot_repo.get_campaigns_by_date(AccountId(str(account.id)), today)
        if not snapshots:
            yesterday = today - _dt.timedelta(days=1)
            snapshots = await snapshot_repo.get_campaigns_by_date(AccountId(str(account.id)), yesterday)

        campaigns = []
        for snap in snapshots:
            if snap.channel_type != "PERFORMANCE_MAX":
                continue
            daily_budget_pln = snap.budget_micros / 1_000_000 if snap.budget_micros else None
            roas = None
            if snap.cost_micros and snap.cost_micros > 0 and snap.conv_value:
                roas = round(snap.conv_value / (snap.cost_micros / 1_000_000), 2)
            campaigns.append(
                PMaxCampaignSummary(
                    campaign_resource_name=f"customers/{account.customer_id}/campaigns/{snap.campaign_id}",
                    campaign_name=snap.name,
                    status=snap.status or "UNKNOWN",
                    daily_budget_pln=round(daily_budget_pln, 2) if daily_budget_pln else None,
                    impressions=snap.impressions,
                    clicks=snap.clicks,
                    conversions=snap.conversions,
                    cost_pln=round(snap.cost_micros / 1_000_000, 2) if snap.cost_micros else None,
                    roas=roas,
                )
            )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()

    return PMaxStatusResponse(campaigns=campaigns)


# ---------------------------------------------------------------------------
# Performance time-series
# ---------------------------------------------------------------------------

class PMaxDailyDataPoint(BaseModel):
    date: str
    impressions: int
    clicks: int
    cost_pln: float
    conversions: float
    conv_value_pln: float
    roas: float | None
    campaign_id: int
    campaign_name: str
    status: str


class AssetGroupHealth(BaseModel):
    campaign_id: int
    campaign_name: str
    status: str
    has_disapproved_assets: bool


class PMaxPerformanceResponse(BaseModel):
    time_series: list[PMaxDailyDataPoint]
    asset_group_health: list[AssetGroupHealth]
    days: int


@router.get("/{user_id}/pmax/performance", response_model=PMaxPerformanceResponse)
async def get_pmax_performance(
    user_id: str,
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    days: int = 30,
) -> PMaxPerformanceResponse:
    """Return PMax time-series metrics for Recharts visualisation (last N days)."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="days must be between 1 and 90")

    session, engine, account, creds = await _get_session_and_account(user_id, account_id, settings)
    try:
        import datetime as _dt
        from adcopilot.domain.entities import AccountId
        from adcopilot.domain.recommendation import RecommendationKind, RecommendationStatus
        from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository
        from adcopilot.infrastructure.db.models import RecommendationModel
        from sqlalchemy import select

        end_date = _dt.date.today()
        start_date = end_date - _dt.timedelta(days=days - 1)

        snapshot_repo = SqlSnapshotRepository(session)
        all_snaps = await snapshot_repo.get_campaigns_date_range(
            AccountId(str(account.id)), start_date, end_date
        )
        pmax_snaps = [s for s in all_snaps if s.channel_type == "PERFORMANCE_MAX"]

        # Build time-series data points
        time_series: list[PMaxDailyDataPoint] = []
        for snap in pmax_snaps:
            roas = None
            if snap.cost_micros and snap.cost_micros > 0 and snap.conv_value:
                roas = round(snap.conv_value / (snap.cost_micros / 1_000_000), 2)
            time_series.append(
                PMaxDailyDataPoint(
                    date=snap.snapshot_date.isoformat(),
                    impressions=snap.impressions,
                    clicks=snap.clicks,
                    cost_pln=round(snap.cost_micros / 1_000_000, 2) if snap.cost_micros else 0.0,
                    conversions=snap.conversions,
                    conv_value_pln=round(snap.conv_value, 2) if snap.conv_value else 0.0,
                    roas=roas,
                    campaign_id=snap.campaign_id,
                    campaign_name=snap.name,
                    status=snap.status or "UNKNOWN",
                )
            )

        # Asset group health: check for recent PMAX_ASSET_DISAPPROVED recommendations
        disapproved_campaign_ids: set[int] = set()
        result = await session.execute(
            select(RecommendationModel).where(
                RecommendationModel.account_id == __import__("uuid").UUID(str(account.id)),
                RecommendationModel.kind == RecommendationKind.PMAX_ASSET_DISAPPROVED.value,
                RecommendationModel.status == RecommendationStatus.PENDING.value,
            )
        )
        for rec in result.scalars().all():
            if rec.target and isinstance(rec.target, dict):
                cid = rec.target.get("campaign_id")
                if cid:
                    disapproved_campaign_ids.add(int(cid))

        # Get unique PMax campaigns from the time series
        seen: dict[int, str] = {}
        for snap in pmax_snaps:
            seen[snap.campaign_id] = snap.name

        asset_group_health = [
            AssetGroupHealth(
                campaign_id=cid,
                campaign_name=cname,
                status="REVIEW_REQUIRED" if cid in disapproved_campaign_ids else "OK",
                has_disapproved_assets=cid in disapproved_campaign_ids,
            )
            for cid, cname in seen.items()
        ]

    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()

    return PMaxPerformanceResponse(
        time_series=time_series,
        asset_group_health=asset_group_health,
        days=days,
    )
