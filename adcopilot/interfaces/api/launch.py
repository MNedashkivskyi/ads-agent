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
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import get_settings
from adcopilot.infrastructure.vertical_templates.yaml_adapter import YamlVerticalTemplateAdapter
from adcopilot.interfaces.api.auth_middleware import CurrentUser

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
    avg_monthly_searches: int | None = None


class AdResponse(BaseModel):
    headlines: list[str]
    descriptions: list[str]
    final_url: str
    path_segments: list[str]


class AdGroupResponse(BaseModel):
    name: str
    keywords: list[KeywordResponse]
    ads: list[AdResponse]
    intent_tier: str | None = None
    is_brand: bool = False


class CompetitorPreview(BaseModel):
    domain: str
    impression_share: float  # 0..1


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
    # Top competitors from auction insights (live, best-effort). Empty when the
    # account has no auction-insights history yet.
    competitors: list[CompetitorPreview] = []


class VerticalResponse(BaseModel):
    id: str
    display_name: str
    emoji: str
    description: str
    common_services: list[str]


class GenerateProposalRequest(BaseModel):
    template_id: str | None = None
    category_label: str
    selected_services: list[str] = []
    website_url: str | None = None
    location: str
    monthly_budget_pln: float
    primary_action: str = "phone_call"
    account_id: str


class GenerateProposalResponse(BaseModel):
    brief_id: str
    status: str  # "generating"


class ProposalStatusResponse(BaseModel):
    status: str  # "generating" | "ready" | "failed"
    proposal_id: str | None = None


class LaunchProposalResponse(BaseModel):
    status: str  # "launching"
    brief_id: str


class LaunchStatusResponse(BaseModel):
    """Outcome of the background campaign-creation task for a launched brief."""

    status: str  # "creating" | "created" | "failed"
    campaign_resource_name: str | None = None
    message: str | None = None  # human-readable Polish reason, esp. on failure


class ConversionTrackingStatusResponse(BaseModel):
    customer_id: str
    has_conversion_tracking: bool
    conversion_action_count: int
    active_action_names: list[str]


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
    competitors: list[CompetitorPreview] = []
    try:
        async with AsyncSession(engine) as session:
            from adcopilot.domain.launch.entities import CampaignBriefId, CampaignProposalId
            from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
                SqlCampaignProposalRepository,
            )

            repo = SqlCampaignProposalRepository(session)
            proposal = await repo.get(CampaignProposalId(proposal_id))

            # Best-effort live competitor scan for display (account-scoped).
            if proposal is not None:
                try:
                    from datetime import UTC, datetime, timedelta

                    from adcopilot.domain.competitors import top_competitors
                    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
                        SqlCampaignBriefRepository,
                    )
                    from adcopilot.infrastructure.db.repositories.snapshot_repository import (
                        SqlSnapshotRepository,
                    )

                    brief = await SqlCampaignBriefRepository(session).get(
                        CampaignBriefId(str(proposal.brief_id))
                    )
                    if brief is not None:
                        today = datetime.now(tz=UTC).date()
                        rows = await SqlSnapshotRepository(session).get_auction_insights(
                            brief.account_id, today - timedelta(days=14), today
                        )
                        competitors = [
                            CompetitorPreview(domain=c.domain, impression_share=c.impression_share)
                            for c in top_competitors(rows, limit=5)
                        ]
                except Exception:
                    competitors = []
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
                        avg_monthly_searches=kw.avg_monthly_searches,
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
                intent_tier=ag.intent_tier,
                is_brand=ag.is_brand,
            )
            for ag in proposal.ad_groups
        ],
        negative_keywords=proposal.negative_keywords,
        estimated_cpc_min_pln=proposal.estimated_cpc_range[0] / _MICROS_PER_PLN,
        estimated_cpc_max_pln=proposal.estimated_cpc_range[1] / _MICROS_PER_PLN,
        generated_at=proposal.generated_at.isoformat(),
        competitors=competitors,
    )


@api_router.get(
    "/accounts/{account_id}/conversion-tracking",
    response_model=ConversionTrackingStatusResponse,
)
async def check_conversion_tracking(
    account_id: str,
    user_id: CurrentUser,
) -> ConversionTrackingStatusResponse:
    """Check whether a Google Ads account has active macro-conversion tracking.

    Used by the wizard to decide whether to show the conversion setup gate step.
    Returns has_conversion_tracking=false on any API error (fail-open).
    """
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.adapters.google_ads_conversion_adapter import (
        GoogleAdsConversionAdapter,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with AsyncSession(engine) as session:
            creds_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            creds = await creds_repo.get(AccountId(account_id))
            if creds is None:
                raise HTTPException(
                    status_code=404, detail="No OAuth credentials found for account"
                )
            refresh_token = creds.refresh_token
    finally:
        await engine.dispose()

    google_ads_client = GoogleAdsQueriesAdapter(settings)
    adapter = GoogleAdsConversionAdapter(google_ads_client)
    status = await adapter.check(refresh_token, account_id)

    logger.info(
        "conversion_tracking_check",
        account_id=account_id,
        user_id=user_id,
        has_tracking=status.has_conversion_tracking,
    )
    return ConversionTrackingStatusResponse(
        customer_id=status.customer_id,
        has_conversion_tracking=status.has_conversion_tracking,
        conversion_action_count=status.conversion_action_count,
        active_action_names=status.active_action_names,
    )


@api_router.post(
    "/proposals/generate",
    response_model=GenerateProposalResponse,
    status_code=202,
)
async def generate_proposal(
    body: GenerateProposalRequest,
    user_id: CurrentUser,
) -> GenerateProposalResponse:
    """Create a CampaignBrief and dispatch a Celery generation task.

    Returns the brief_id immediately so the client can poll for status.
    The brief status starts at GENERATING; transitions to PROPOSED on success.
    """
    from datetime import UTC, datetime

    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.domain.launch.entities import (
        CampaignBrief,
        CampaignBriefId,
        LaunchStatus,
    )
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.interfaces.worker.tasks import generate_campaign_task

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    brief_id = str(uuid.uuid4())

    description_parts = [body.category_label]
    if body.selected_services:
        description_parts.append(", ".join(body.selected_services[:5]))

    brief = CampaignBrief(
        id=CampaignBriefId(brief_id),
        user_id=UserId(user_id),
        account_id=AccountId(body.account_id),
        business_description=" — ".join(description_parts),
        location=body.location,
        typical_customer_value=Decimal("200"),
        primary_action=body.primary_action,
        monthly_budget_pln=Decimal(str(body.monthly_budget_pln)),
        exclusions=[],
        language="pl",
        created_at=datetime.now(UTC),
        status=LaunchStatus.GENERATING,
    )

    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlCampaignBriefRepository(session)
            await repo.save(brief)
    finally:
        await engine.dispose()

    generate_campaign_task.delay(brief_id, template_id=body.template_id)

    logger.info("generate_proposal submitted", brief_id=brief_id, user_id=user_id)
    return GenerateProposalResponse(brief_id=brief_id, status="generating")


@api_router.get(
    "/proposals/{brief_id}/status",
    response_model=ProposalStatusResponse,
)
async def get_proposal_status(
    brief_id: str,
    user_id: CurrentUser,
) -> ProposalStatusResponse:
    """Poll for campaign proposal generation status.

    Returns `generating`, `ready`, or `failed`.
    When ready, includes the `proposal_id` for the full preview.
    """
    try:
        uuid.UUID(brief_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid brief ID format") from None

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with AsyncSession(engine) as session:
            from adcopilot.domain.launch.entities import (
                CampaignBriefId,
                LaunchStatus,
            )
            from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
                SqlCampaignBriefRepository,
            )
            from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
                SqlCampaignProposalRepository,
            )

            brief_repo = SqlCampaignBriefRepository(session)
            brief = await brief_repo.get(CampaignBriefId(brief_id))

            if brief is None or brief.user_id != user_id:
                raise HTTPException(status_code=404, detail="Brief not found")

            if brief.status == LaunchStatus.PROPOSED:
                proposal_repo = SqlCampaignProposalRepository(session)
                proposal = await proposal_repo.get_by_brief(CampaignBriefId(brief_id))
                proposal_id = str(proposal.id) if proposal else None
                return ProposalStatusResponse(status="ready", proposal_id=proposal_id)

            if brief.status == LaunchStatus.GENERATING:
                return ProposalStatusResponse(status="generating")

            if brief.status == LaunchStatus.FAILED:
                return ProposalStatusResponse(status="failed")

            return ProposalStatusResponse(status="failed")
    finally:
        await engine.dispose()


@api_router.post(
    "/proposals/{proposal_id}/launch",
    response_model=LaunchProposalResponse,
    status_code=202,
)
async def launch_proposal(
    proposal_id: str,
    user_id: CurrentUser,
) -> LaunchProposalResponse:
    """Approve a proposal and enqueue campaign creation — no setup fee.

    This is the free-launch path: it performs the same work the Stripe
    webhook used to do after a successful setup-fee payment (transition the
    brief to APPROVED and dispatch ``create_campaign_task``), but skips the
    payment step entirely.
    """
    import dataclasses

    try:
        uuid.UUID(proposal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid proposal ID format") from None

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        from adcopilot.domain.launch.entities import (
            CampaignBriefId,
            CampaignProposalId,
            LaunchStatus,
        )
        from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
            SqlCampaignBriefRepository,
        )
        from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
            SqlCampaignProposalRepository,
        )

        async with AsyncSession(engine) as session, session.begin():
            proposal_repo = SqlCampaignProposalRepository(session)
            proposal = await proposal_repo.get(CampaignProposalId(proposal_id))
            if proposal is None:
                raise HTTPException(status_code=404, detail="Proposal not found")

            brief_id = str(proposal.brief_id)
            brief_repo = SqlCampaignBriefRepository(session)
            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None or brief.user_id != user_id:
                raise HTTPException(status_code=404, detail="Brief not found")
            if brief.status not in (LaunchStatus.PROPOSED, LaunchStatus.APPROVED):
                raise HTTPException(
                    status_code=409,
                    detail=f"Brief is in status '{brief.status}', expected 'proposed'",
                )
            updated = dataclasses.replace(brief, status=LaunchStatus.APPROVED)
            await brief_repo.save(updated)
    finally:
        await engine.dispose()

    from adcopilot.interfaces.worker.tasks import create_campaign_task

    create_campaign_task.delay(brief_id)
    logger.info("proposal launched without setup fee", proposal_id=proposal_id, brief_id=brief_id)
    return LaunchProposalResponse(status="launching", brief_id=brief_id)


class EnableCampaignRequest(BaseModel):
    override_conversion_check: bool = False


class EnableCampaignResponse(BaseModel):
    status: str  # "enabling"
    brief_id: str


@api_router.post(
    "/launch/{brief_id}/enable",
    response_model=EnableCampaignResponse,
    status_code=202,
)
async def enable_campaign(
    brief_id: str,
    user_id: CurrentUser,
    body: EnableCampaignRequest | None = None,
) -> EnableCampaignResponse:
    """Enable a PAUSED campaign (go live). Gated on conversion tracking for
    conversion-goal campaigns unless ``override_conversion_check`` is set.

    Returns 409 with ``{error, message_pl}`` when blocked so the frontend can
    route the user to tracking setup (or retry with the override).
    """
    override = bool(body and body.override_conversion_check)

    from adcopilot.application.use_cases.launch.check_conversion_setup import (
        goal_requires_tracking,
        has_macro_conversion_tracking,
    )
    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.launch.entities import CampaignBriefId, LaunchStatus
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            brief = await SqlCampaignBriefRepository(session).get(CampaignBriefId(brief_id))
            if brief is None or brief.user_id != user_id:
                raise HTTPException(status_code=404, detail="Brief not found")
            if brief.status != LaunchStatus.CREATED_PAUSED:
                raise HTTPException(
                    status_code=409,
                    detail=f"Brief is in status '{brief.status}', expected 'created_paused'",
                )

            account = await SqlGoogleAdsAccountRepository(session).get(brief.account_id)
            if account is None:
                raise HTTPException(status_code=404, detail="Account not found")
            credentials = await SqlOAuthCredentialsRepository(
                session, settings.TOKEN_ENCRYPTION_KEY
            ).get(AccountId(account.id))
            if credentials is None:
                raise HTTPException(status_code=422, detail="Google Ads account not connected")

        # Conversion-tracking gate (synchronous, for immediate UX). The worker
        # task re-checks as defense-in-depth.
        if not override and goal_requires_tracking(brief.primary_action):
            try:
                actions = await GoogleAdsQueriesAdapter(settings).list_conversion_actions(
                    credentials.refresh_token, account.customer_id
                )
            except Exception as exc:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "tracking_check_failed",
                        "message_pl": (
                            "Nie udało się zweryfikować śledzenia konwersji. "
                            "Spróbuj ponownie za chwilę."
                        ),
                    },
                ) from exc
            if not has_macro_conversion_tracking(actions):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "no_conversion_tracking",
                        "message_pl": (
                            "Kampania z tym celem wymaga skonfigurowanego śledzenia "
                            "konwersji przed uruchomieniem. Skonfiguruj śledzenie lub "
                            "uruchom mimo to (override)."
                        ),
                    },
                )
    finally:
        await engine.dispose()

    from adcopilot.interfaces.worker.tasks import enable_campaign_task

    enable_campaign_task.delay(brief_id, skip_conversion_check=override)
    logger.info("campaign enable requested", brief_id=brief_id, override=override)
    return EnableCampaignResponse(status="enabling", brief_id=brief_id)


@api_router.get(
    "/proposals/{brief_id}/launch-status",
    response_model=LaunchStatusResponse,
)
async def get_launch_status(
    brief_id: str,
    user_id: CurrentUser,
) -> LaunchStatusResponse:
    """Poll the outcome of the background campaign-creation task.

    Returns ``creating`` while the Celery task runs, ``created`` once the
    brief reaches CREATED_PAUSED/ENABLED (with the campaign resource name),
    or ``failed`` with a human-readable Polish reason taken from the failure
    notification the worker persisted. Lets the launch UI show a real
    success/failure result instead of silently redirecting to the dashboard.
    """
    try:
        uuid.UUID(brief_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid brief ID format") from None

    from sqlalchemy import select

    from adcopilot.domain.launch.entities import CampaignBriefId, LaunchStatus
    from adcopilot.infrastructure.db.models import NotificationModel
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            brief_repo = SqlCampaignBriefRepository(session)
            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None or brief.user_id != user_id:
                raise HTTPException(status_code=404, detail="Brief not found")

            if brief.status in (LaunchStatus.CREATED_PAUSED, LaunchStatus.ENABLED):
                return LaunchStatusResponse(
                    status="created",
                    campaign_resource_name=brief.campaign_resource_name,
                )

            # No terminal success yet — check whether the worker recorded a
            # failure notification for this brief (it carries the error reason).
            stmt = (
                select(NotificationModel)
                .where(NotificationModel.user_id == str(user_id))
                .where(NotificationModel.metadata_["brief_id"].astext == brief_id)
                .order_by(NotificationModel.created_at.desc())
                .limit(1)
            )
            notif = (await session.execute(stmt)).scalars().first()
            if notif is not None and (notif.metadata_ or {}).get("error"):
                return LaunchStatusResponse(status="failed", message=notif.body)

            return LaunchStatusResponse(status="creating")
    finally:
        await engine.dispose()
