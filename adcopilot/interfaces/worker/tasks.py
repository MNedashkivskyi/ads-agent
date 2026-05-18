"""Celery tasks for snapshot ingestion, campaign launch, and monitoring."""

from __future__ import annotations

import uuid
from datetime import UTC, date

import structlog
from redis import Redis

from adcopilot.application.use_cases.snapshot_account import SnapshotResult
from adcopilot.interfaces.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

_LOCK_TTL_SECONDS = 7200  # 2 hours
_MONITORING_INTERVAL_SECONDS = 3600  # 1 hour
_MONITORING_WINDOW_HOURS = 48


def _redis_client() -> Redis:  # type: ignore[type-arg]
    from adcopilot.config import get_settings

    settings = get_settings()
    return Redis.from_url(settings.REDIS_URL)


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    name="adcopilot.interfaces.worker.tasks.snapshot_account_task",
)
def snapshot_account_task(account_id: str, snapshot_date_iso: str) -> dict[str, object]:
    """Pull a full snapshot for one account on the given date."""
    import asyncio

    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId

    settings = get_settings()
    snap_date = date.fromisoformat(snapshot_date_iso)
    lock_key = f"lock:snapshot:{account_id}:{snapshot_date_iso}"

    redis = _redis_client()
    # Per-account Redis lock — skip if already held
    acquired = redis.set(lock_key, "1", nx=True, ex=_LOCK_TTL_SECONDS)
    if not acquired:
        logger.warning(
            "snapshot already in progress, skipping",
            account_id=account_id,
            date=snapshot_date_iso,
        )
        return {"skipped": True}

    try:
        result = asyncio.run(_run_snapshot(settings, AccountId(account_id), snap_date))
        # If the snapshot failed due to an auth error the use case already set
        # needs_reauth=True on the account.  Notify the user so they know to
        # reconnect their Google Ads account.
        if not result.success and "GoogleAdsAuthError" in (result.error_message or ""):
                # TODO(phase-1): send reauth notification via new notifier
                logger.warning(
                    "snapshot auth failure — user needs to reconnect Google Ads",
                    account_id=account_id,
                )
        if result.success:
            # Run detection asynchronously after a successful snapshot
            asyncio.run(_run_detection(settings, AccountId(account_id), snap_date))
        return {
            "account_id": account_id,
            "snapshot_date": snapshot_date_iso,
            "campaigns": result.campaigns,
            "ad_groups": result.ad_groups,
            "keywords": result.keywords,
            "search_terms": result.search_terms,
            "ads": result.ads,
            "duration_seconds": result.duration_seconds,
            "success": result.success,
        }
    finally:
        redis.delete(lock_key)


async def _run_snapshot(settings: object, account_id: object, snap_date: date) -> SnapshotResult:
    """Run the use case inside an async context with its own DB session."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.snapshot_account import SnapshotAccountUseCase
    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    assert isinstance(settings, Settings)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            use_case = SnapshotAccountUseCase(
                ads_client=GoogleAdsQueriesAdapter(settings),
                snapshot_repo=SqlSnapshotRepository(session),
                credentials_repo=SqlOAuthCredentialsRepository(
                    session, settings.TOKEN_ENCRYPTION_KEY
                ),
                account_repo=SqlGoogleAdsAccountRepository(session),
            )
            result = await use_case.execute(AccountId(str(account_id)), snap_date)
            _save_run(session, result)
            return result
    finally:
        await engine.dispose()


async def _run_detection(settings: object, account_id: object, snap_date: date) -> None:
    """Run the detection engine after a successful snapshot."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.run_detection import RunDetectionUseCase
    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository

    assert isinstance(settings, Settings)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            from adcopilot.application.detection.registry import build_rule_engine
            from adcopilot.infrastructure.db.repositories.recommendation_repository import (
                SqlRecommendationRepository,
            )
            from adcopilot.infrastructure.db.repositories.snooze_repository import (
                SqlSnoozeRepository,
            )

            rec_repo = SqlRecommendationRepository(session)
            snooze_repo = SqlSnoozeRepository(session)
            rule_engine = build_rule_engine(rec_repo, snooze_repo)
            use_case = RunDetectionUseCase(
                snapshot_repo=SqlSnapshotRepository(session),
                rec_repo=rec_repo,
                rule_engine=rule_engine,
                account_repo=SqlGoogleAdsAccountRepository(session),
            )
            await use_case.execute(AccountId(str(account_id)), snap_date)
    except Exception:
        logger.exception("detection failed (non-fatal)", account_id=str(account_id))
    finally:
        await engine.dispose()


def _save_run(session: object, result: SnapshotResult) -> None:
    """Persist snapshot run metadata (fire and forget within the same session)."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from adcopilot.infrastructure.db.models import SnapshotRunModel

    assert isinstance(session, AsyncSession)
    run = SnapshotRunModel()
    run.id = uuid.uuid4()
    run.account_id = uuid.UUID(result.account_id)
    run.snapshot_date = result.snapshot_date
    run.status = "success" if result.success else "failed"
    run.campaigns = result.campaigns
    run.ad_groups = result.ad_groups
    run.keywords = result.keywords
    run.search_terms = result.search_terms
    run.ads = result.ads
    run.duration_seconds = result.duration_seconds
    run.error_message = result.error_message
    session.add(run)


@celery_app.task(name="adcopilot.interfaces.worker.tasks.send_daily_digests_task")  # type: ignore[untyped-decorator]
def send_daily_digests_task() -> dict[str, object]:
    """Send daily recommendation digests to all users."""
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()
    results = asyncio.run(_run_send_digests(settings))
    logger.info("daily digests sent", **results)
    return results


async def _run_send_digests(settings: object) -> dict[str, object]:
    """Compute digests for all users (log-only; notifier wired in Phase 1)."""
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.send_daily_digest import SendDailyDigestUseCase
    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.digest_sent_log_repository import (
        SqlDigestSentLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )
    assert isinstance(settings, Settings)

    today = datetime.now(UTC).date()
    engine = create_async_engine(settings.DATABASE_URL)
    sent = 0
    skipped = 0
    try:
        from sqlalchemy import select

        async with AsyncSession(engine) as session, session.begin():
            result = await session.execute(
                select(UserModel).where(
                    UserModel.notifications_paused.is_(False),
                )
            )
            users = result.scalars().all()

        # TODO(phase-1): wire new notifier implementation
        logger.warning("digest_notifier not configured, skipping digest sends")
        return {"sent": 0, "skipped": len(users), "reason": "notifier_not_configured"}
    finally:
        await engine.dispose()


@celery_app.task(name="adcopilot.interfaces.worker.tasks.run_nightly_snapshots")  # type: ignore[untyped-decorator]
def run_nightly_snapshots() -> dict[str, object]:
    """Queue snapshot tasks for all active accounts."""
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()
    today = date.today().isoformat()

    async def _list_accounts() -> list[str]:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )

        engine = create_async_engine(settings.DATABASE_URL)
        try:
            async with AsyncSession(engine) as session:
                repo = SqlGoogleAdsAccountRepository(session)
                accounts = await repo.list_active()
                return [str(a.id) for a in accounts]
        finally:
            await engine.dispose()

    account_ids = asyncio.run(_list_accounts())
    for aid in account_ids:
        snapshot_account_task.delay(aid, today)

    logger.info("nightly snapshots queued", count=len(account_ids), date=today)
    return {"queued": len(account_ids), "date": today}


@celery_app.task(name="adcopilot.interfaces.worker.tasks.send_trial_reminders_task")  # type: ignore[untyped-decorator]
def send_trial_reminders_task() -> dict[str, object]:
    """Send trial-ending reminder on day 12 of trial."""
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()
    results = asyncio.run(_run_trial_reminders(settings))
    logger.info("trial reminders sent", **results)
    return results


async def _run_trial_reminders(settings: object) -> dict[str, object]:
    from datetime import datetime, timedelta

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import Settings
    from adcopilot.infrastructure.db.models import UserModel

    assert isinstance(settings, Settings)

    now = datetime.now(UTC)
    # Day 12 = trial_ends_at is within 2 days from now
    reminder_window_start = now + timedelta(days=1, hours=23)
    reminder_window_end = now + timedelta(days=2, hours=1)

    engine = create_async_engine(settings.DATABASE_URL)
    sent = 0
    skipped = 0
    try:
        async with AsyncSession(engine) as session, session.begin():
            result = await session.execute(
                select(UserModel).where(
                    UserModel.subscription_status == "trialing",
                    UserModel.trial_ends_at.isnot(None),
                    UserModel.trial_ends_at >= reminder_window_start,
                    UserModel.trial_ends_at <= reminder_window_end,
                )
            )
            users = result.scalars().all()

        # TODO(phase-0.2): wire new notifier implementation
        logger.warning("trial_reminder_notifier not configured, skipping")
        skipped = len(users)
    finally:
        await engine.dispose()

    return {"sent": sent, "skipped": skipped}


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    retry_backoff=True,
    retry_backoff_max=300,
    name="adcopilot.interfaces.worker.tasks.execute_recommendation_task",
)
def execute_recommendation_task(self: object, rec_id: str) -> dict[str, object]:
    """Execute a single APPROVED recommendation against the Google Ads API.

    Auth errors (revoked/expired refresh token) are caught immediately and
    treated as permanent failures — retrying with the same bad token is
    pointless.  For all other exceptions the task retries up to max_retries
    times with exponential back-off; after the final retry the recommendation
    is marked FAILED and the user receives a Telegram notification.
    """
    import asyncio

    from celery import Task  # type: ignore[import-untyped]

    from adcopilot.domain.exceptions import GoogleAdsAuthError

    assert isinstance(self, Task)
    try:
        return asyncio.run(_run_execute_recommendation(rec_id))
    except GoogleAdsAuthError:
        # Permanent auth failure — mark rec FAILED, set needs_reauth, notify user.
        try:
            asyncio.run(_handle_auth_failure(rec_id))
        except Exception:
            logger.exception("failed to handle auth failure", rec_id=rec_id)
        raise
    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc
        # All retries exhausted — mark FAILED and notify the user.
        error_message = str(exc) or type(exc).__name__
        try:
            asyncio.run(_handle_execution_failure(rec_id, error_message))
        except Exception:
            logger.exception("failed to handle execution failure", rec_id=rec_id)
        raise


async def _run_execute_recommendation(rec_id: str) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.execute_recommendation import ExecuteRecommendationUseCase
    from adcopilot.config import get_settings
    from adcopilot.domain.recommendation import RecommendationId
    from adcopilot.infrastructure.db.repositories.audit_log_repository import SqlAuditLogRepository
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            use_case = ExecuteRecommendationUseCase(
                rec_repo=SqlRecommendationRepository(session),
                audit_log_repo=SqlAuditLogRepository(session),
                account_repo=SqlGoogleAdsAccountRepository(session),
                credentials_repo=SqlOAuthCredentialsRepository(
                    session, settings.TOKEN_ENCRYPTION_KEY
                ),
                mutations=GoogleAdsMutationsAdapter(settings),
            )
            result = await use_case.execute(RecommendationId(rec_id))
    finally:
        await engine.dispose()

    logger.info("recommendation executed", rec_id=rec_id)
    return {"rec_id": rec_id, "result": result}


async def _handle_auth_failure(rec_id: str) -> None:
    """Mark rec FAILED, set account.needs_reauth=True, and send a reauth notification."""
    import dataclasses

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.recommendation import RecommendationId, RecommendationStatus
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            rec_repo = SqlRecommendationRepository(session)
            rec = await rec_repo.get(RecommendationId(rec_id))
            if rec is None:
                logger.error("recommendation not found during auth failure handling", rec_id=rec_id)
                return

            await rec_repo.update_status(RecommendationId(rec_id), RecommendationStatus.FAILED)

            account_repo = SqlGoogleAdsAccountRepository(session)
            account = await account_repo.get(rec.account_id)
            if account is None:
                return

            # Persist needs_reauth flag so the account is excluded from future
            # nightly snapshots until the user reconnects.
            updated_account = dataclasses.replace(account, needs_reauth=True)
            await account_repo.save(updated_account)
            logger.warning(
                "account marked needs_reauth after auth failure",
                account_id=account.id,
                rec_id=rec_id,
            )
            # TODO(phase-1): send reauth notification via new notifier
    finally:
        await engine.dispose()



async def _handle_execution_failure(rec_id: str, error_message: str) -> None:
    """Mark the recommendation FAILED and log the failure (notification wired in Phase 1)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.recommendation import RecommendationId, RecommendationStatus
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            rec_repo = SqlRecommendationRepository(session)
            rec = await rec_repo.get(RecommendationId(rec_id))
            if rec is None:
                logger.error("recommendation not found during failure handling", rec_id=rec_id)
                return

            await rec_repo.update_status(RecommendationId(rec_id), RecommendationStatus.FAILED)
            logger.warning(
                "recommendation marked FAILED",
                rec_id=rec_id,
                kind=rec.kind.value,
                error=error_message,
            )
            # TODO(phase-1): send execution failed notification via new notifier
    finally:
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.generate_campaign_task",
)
def generate_campaign_task(
    brief_id: str,
    revision_text: str | None = None,
) -> dict[str, object]:
    """Generate a campaign proposal (log-only; notification wired in Phase 1).

    Dispatched when the user submits a campaign brief or revision.
    """
    import asyncio

    return asyncio.run(_run_generate_campaign(brief_id, revision_text))


async def _run_generate_campaign(
    brief_id: str,
    revision_text: str | None,
) -> dict[str, object]:
    """Run the proposal-generation pipeline (log-only; notification wired in Phase 1)."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.launch.generate_proposal import (
        GenerateCampaignProposalUseCase,
    )
    from adcopilot.config import get_settings
    from adcopilot.domain.launch.entities import CampaignBriefId
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
        SqlCampaignProposalRepository,
    )
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
    from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    proposal_id: str | None = None
    error_text: str | None = None

    try:
        async with AsyncSession(engine) as session, session.begin():
            brief_repo = SqlCampaignBriefRepository(session)
            proposal_repo = SqlCampaignProposalRepository(session)

            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None:
                logger.error("generate_campaign_task: brief not found", brief_id=brief_id)
                return {"error": "brief_not_found"}

            if not settings.LLM_API_KEY:
                from adcopilot.domain.launch.entities import LaunchStatus
                from adcopilot.domain.launch.templates import build_proposal_from_template
                proposal = build_proposal_from_template(brief)
                await proposal_repo.save(proposal)
                await brief_repo.update_status(brief.id, LaunchStatus.PROPOSED)
            else:
                llm = AnthropicClient(api_key=settings.LLM_API_KEY)
                generator = CampaignGenerator(llm)
                use_case = GenerateCampaignProposalUseCase(
                    brief_repo=brief_repo,
                    proposal_repo=proposal_repo,
                    generator=generator,
                )
                proposal = await use_case.execute(brief, revision_feedback=revision_text)

            proposal_id = str(proposal.id)

    except Exception as exc:
        logger.exception("generate_campaign_task failed", brief_id=brief_id)
        error_text = str(exc)[:200]
    finally:
        await engine.dispose()

    # TODO(phase-0.2): send proposal notification via new notifier
    return {"proposal_id": proposal_id, "error": error_text}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.create_campaign_task",
)
def create_campaign_task(brief_id: str) -> dict[str, object]:
    """Create the full campaign in Google Ads (PAUSED).

    Dispatched when the user confirms campaign creation.
    """
    import asyncio

    return asyncio.run(_run_create_campaign(brief_id))


async def _run_create_campaign(brief_id: str) -> dict[str, object]:
    import dataclasses

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.ports.campaign_writer import CreatedCampaignResources
    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.launch.entities import CampaignBriefId, LaunchStatus
    from adcopilot.infrastructure.db.repositories.audit_log_repository import (
        SqlAuditLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
        SqlCampaignProposalRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.campaign_writer import CampaignWriter

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    error_text: str | None = None
    campaign_rn: str | None = None
    _saved_refresh_token: str | None = None
    _saved_customer_id: str | None = None
    _saved_primary_action: str | None = None

    try:
        async with AsyncSession(engine) as session, session.begin():
            brief_repo = SqlCampaignBriefRepository(session)
            proposal_repo = SqlCampaignProposalRepository(session)
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            audit_repo = SqlAuditLogRepository(session)

            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None:
                return {"error": "brief_not_found"}

            proposal = await proposal_repo.get_by_brief(brief.id)
            if proposal is None:
                return {"error": "proposal_not_found"}

            account = await account_repo.get(brief.account_id)
            if account is None:
                return {"error": "account_not_found"}

            credentials = await credentials_repo.get(AccountId(account.id))
            if credentials is None:
                return {"error": "credentials_not_found"}
            _saved_refresh_token = credentials.refresh_token
            _saved_customer_id = account.customer_id
            _saved_primary_action = brief.primary_action


            writer = CampaignWriter(
                settings=settings,
                audit_log_repo=audit_repo,
                account_id=AccountId(account.id),
            )

            # Track all created resources for potential rollback
            ad_rns: list[str] = []
            kw_rns: list[str] = []
            neg_rns: list[str] = []
            ext_rns: list[str] = []
            ag_rns: list[str] = []
            audience_rns: list[str] = []
            brand_campaign_rn: str = ""
            brand_budget_rn: str = ""
            schedule_rns: list[str] = []

            try:
                campaign_rn, budget_rn = await writer.create_campaign(
                    account.customer_id, credentials.refresh_token, proposal
                )
                ag_rns = await writer.create_ad_groups(
                    account.customer_id,
                    credentials.refresh_token,
                    campaign_rn,
                    proposal.ad_groups,
                )
                for ag_rn, ag_proposal in zip(ag_rns, proposal.ad_groups, strict=False):
                    kws = await writer.create_keywords(
                        account.customer_id,
                        credentials.refresh_token,
                        ag_rn,
                        ag_proposal.keywords,
                    )
                    kw_rns.extend(kws)
                    ads = await writer.create_ads(
                        account.customer_id,
                        credentials.refresh_token,
                        ag_rn,
                        ag_proposal.ads,
                    )
                    ad_rns.extend(ads)

                # Add observation-mode audience signals for MID/GROWTH tiers
                from adcopilot.domain.launch.audience_signals import get_audience_signals
                from adcopilot.domain.launch.budget_tier import classify_budget_tier
                from adcopilot.domain.launch.schedule_rules import get_ad_schedule
                from adcopilot.domain.launch.templates import detect_vertical_from_description
                _tier = classify_budget_tier(brief.monthly_budget_pln)
                _vertical = detect_vertical_from_description(brief.business_description)

                # Apply ad schedule (dayparting) based on vertical and tier
                _schedule = get_ad_schedule(_vertical, _tier)
                if _schedule:
                    schedule_rns = await writer.create_ad_schedule(
                        account.customer_id,
                        credentials.refresh_token,
                        campaign_rn,
                        _schedule,
                    )
                _audience_signals = get_audience_signals(_vertical, _tier)
                if _audience_signals:
                    audience_rns = await writer.create_audience_signals(
                        account.customer_id,
                        credentials.refresh_token,
                        ag_rns,
                        _audience_signals,
                    )

                neg_rns = await writer.create_negative_keywords(
                    account.customer_id,
                    credentials.refresh_token,
                    campaign_rn,
                    proposal.negative_keywords,
                )

                ext_rns = await writer.create_extensions(
                    account.customer_id,
                    credentials.refresh_token,
                    campaign_rn,
                    proposal.sitelinks,
                    proposal.callouts,
                    proposal.structured_snippets,
                )

                # Create brand campaign for MID/GROWTH tiers
                if proposal.brand_campaign_name:
                    brand_campaign_rn, brand_budget_rn = await writer.create_brand_campaign(
                        account.customer_id,
                        credentials.refresh_token,
                        proposal,
                    )

                # Persist campaign resource name + update status
                updated_brief = dataclasses.replace(
                    brief,
                    status=LaunchStatus.CREATED_PAUSED,
                    campaign_resource_name=campaign_rn,
                )
                await brief_repo.save(updated_brief)

            except Exception:
                logger.exception(
                    "campaign creation failed — rolling back",
                    brief_id=brief_id,
                )
                # Rollback everything created so far
                if campaign_rn or ag_rns or kw_rns or ad_rns or neg_rns or ext_rns or audience_rns or brand_campaign_rn or schedule_rns:
                    resources = CreatedCampaignResources(
                        campaign_resource_name=campaign_rn or "",
                        budget_resource_name=budget_rn if "budget_rn" in dir() else "",
                        ad_group_resource_names=ag_rns,
                        keyword_resource_names=kw_rns,
                        ad_resource_names=ad_rns,
                        negative_resource_names=neg_rns,
                        extension_resource_names=ext_rns,
                        audience_resource_names=audience_rns,
                        brand_campaign_resource_name=brand_campaign_rn,
                        brand_budget_resource_name=brand_budget_rn,
                        schedule_resource_names=schedule_rns,
                    )
                    try:
                        await writer.delete_draft_campaign(
                            account.customer_id, credentials.refresh_token, resources
                        )
                    except Exception:
                        logger.exception("rollback failed", brief_id=brief_id)
                raise

    except Exception as exc:
        logger.exception("create_campaign_task failed", brief_id=brief_id)
        error_text = str(exc)[:200]
    finally:
        await engine.dispose()

    # TODO(phase-0.2): send campaign created notification via new notifier
    return {"campaign_rn": campaign_rn, "error": error_text}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.enable_campaign_task",
)
def enable_campaign_task(brief_id: str) -> dict[str, object]:
    """Enable the paused campaign and start monitoring.

    Dispatched when the user confirms enabling.
    """
    import asyncio

    return asyncio.run(_run_enable_campaign(brief_id))


async def _run_enable_campaign(brief_id: str) -> dict[str, object]:
    import dataclasses

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.launch.entities import CampaignBriefId, LaunchStatus
    from adcopilot.infrastructure.db.repositories.audit_log_repository import (
        SqlAuditLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.campaign_writer import CampaignWriter

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    error_text: str | None = None
    account_id_str: str | None = None

    try:
        async with AsyncSession(engine) as session, session.begin():
            brief_repo = SqlCampaignBriefRepository(session)
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            audit_repo = SqlAuditLogRepository(session)

            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None:
                return {"error": "brief_not_found"}
            if not brief.campaign_resource_name:
                return {"error": "campaign_resource_name_missing"}

            account = await account_repo.get(brief.account_id)
            if account is None:
                return {"error": "account_not_found"}
            account_id_str = str(account.id)

            credentials = await credentials_repo.get(AccountId(account.id))
            if credentials is None:
                return {"error": "credentials_not_found"}

            writer = CampaignWriter(
                settings=settings,
                audit_log_repo=audit_repo,
                account_id=AccountId(account.id),
            )
            await writer.enable_campaign(
                account.customer_id,
                credentials.refresh_token,
                brief.campaign_resource_name,
            )

            updated_brief = dataclasses.replace(brief, status=LaunchStatus.ENABLED)
            await brief_repo.save(updated_brief)

    except Exception as exc:
        logger.exception("enable_campaign_task failed", brief_id=brief_id)
        error_text = str(exc)[:200]
    finally:
        await engine.dispose()

    # TODO(phase-0.2): send enable notification via new notifier

    # Schedule 48-hour high-alert monitoring (hourly checks)
    if not error_text and account_id_str:
        monitor_new_campaign_task.apply_async(
            args=[brief_id, account_id_str, 1],
            countdown=_MONITORING_INTERVAL_SECONDS,
        )
        logger.info(
            "48h monitoring scheduled",
            brief_id=brief_id,
            account_id=account_id_str,
        )

    return {"enabled": not bool(error_text)}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=2,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.monitor_new_campaign_task",
)
def monitor_new_campaign_task(
    brief_id: str,
    account_id: str,
    hours_elapsed: int,
) -> dict[str, object]:
    """Run anomaly detection for a newly-enabled campaign, hourly for 48 hours.

    After 48 hours the monitoring window closes and nightly digests take over.
    """
    import asyncio

    return asyncio.run(
        _run_monitor_new_campaign(brief_id, account_id, hours_elapsed)
    )


async def _run_monitor_new_campaign(
    brief_id: str,
    account_id: str,
    hours_elapsed: int,
) -> dict[str, object]:
    from datetime import datetime, timedelta

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.domain.launch.entities import CampaignBriefId, LaunchStatus
    from adcopilot.infrastructure.db.models import RecommendationModel
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    settings = get_settings()

    # Verify campaign is still ENABLED
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            brief_repo = SqlCampaignBriefRepository(session)
            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None or brief.status != LaunchStatus.ENABLED:
                logger.info(
                    "monitor_new_campaign: campaign no longer enabled, stopping",
                    brief_id=brief_id,
                )
                return {"stopped": True, "reason": "not_enabled"}
    finally:
        await engine.dispose()

    # Run a fresh snapshot + detection pass
    today = date.today()
    try:
        snap_result = await _run_snapshot(settings, AccountId(account_id), today)
        if snap_result.success:
            await _run_detection(settings, AccountId(account_id), today)
    except Exception:
        logger.exception(
            "monitor_new_campaign snapshot/detection failed (non-fatal)",
            account_id=account_id,
        )

    # Look for high-impact recommendations created in the last 2 hours
    alerts_sent = 0
    engine2 = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine2) as session:
            import uuid as _uuid

            since = datetime.now(UTC) - timedelta(hours=2)
            result = await session.execute(
                select(RecommendationModel)
                .where(
                    RecommendationModel.account_id == _uuid.UUID(account_id),
                    RecommendationModel.created_at >= since,
                )
                .order_by(RecommendationModel.estimated_monthly_savings_micros.desc())
                .limit(3)
            )
            new_recs = result.scalars().all()

            if new_recs:
                # TODO(phase-0.2): send early alerts via new notifier
                alerts_sent = len(new_recs)
    finally:
        await engine2.dispose()

    # Schedule next check if still within the 48-hour window
    if hours_elapsed < _MONITORING_WINDOW_HOURS:
        monitor_new_campaign_task.apply_async(
            args=[brief_id, account_id, hours_elapsed + 1],
            countdown=_MONITORING_INTERVAL_SECONDS,
        )
        logger.info(
            "next monitoring check scheduled",
            brief_id=brief_id,
            hours_elapsed=hours_elapsed + 1,
        )
    else:
        # 48-hour window complete — revert to standard daily digest
        # TODO(phase-0.2): send monitoring complete notification via new notifier
        logger.info(
            "48h monitoring window complete",
            brief_id=brief_id,
            account_id=account_id,
        )

    return {"hours_elapsed": hours_elapsed, "alerts_sent": alerts_sent}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=2,
    default_retry_delay=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.panic_pause_campaigns_task",
)
def panic_pause_campaigns_task(account_id: str) -> dict[str, object]:
    """Pause all ENABLED campaigns in *account_id* immediately.

    Target: complete within 30 seconds.
    """
    import asyncio

    return asyncio.run(_run_panic_pause(account_id))


async def _run_panic_pause(account_id: str) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.audit_log_repository import (
        SqlAuditLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    paused_count = 0
    error_text: str | None = None

    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            audit_repo = SqlAuditLogRepository(session)

            account = await account_repo.get(AccountId(account_id))
            if account is None:
                return {"error": "account_not_found"}

            credentials = await credentials_repo.get(AccountId(account_id))
            if credentials is None:
                return {"error": "credentials_not_found"}

            paused_count = await _pause_all_enabled_campaigns(
                settings=settings,
                customer_id=account.customer_id,
                refresh_token=credentials.refresh_token,
                account_id=AccountId(account_id),
                audit_repo=audit_repo,
            )

    except Exception as exc:
        logger.exception("panic_pause_campaigns_task failed", account_id=account_id)
        error_text = str(exc)[:200]
    finally:
        await engine.dispose()

    # TODO(phase-0.2): send panic pause notification via new notifier
    return {"paused": paused_count, "error": error_text}


async def _pause_all_enabled_campaigns(
    settings: object,
    customer_id: str,
    refresh_token: str,
    account_id: object,
    audit_repo: object,
) -> int:
    """Query the Google Ads API for ENABLED campaigns and pause them all.

    Returns the number of campaigns paused.
    """
    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter

    assert isinstance(settings, Settings)
    account_id_typed = AccountId(str(account_id))

    adapter = GoogleAdsClientAdapter(settings)
    client = adapter._build_client(refresh_token)
    cid = customer_id.replace("-", "")

    # Query for all ENABLED campaigns in this account
    ga_service = client.get_service("GoogleAdsService")
    query = """
        SELECT campaign.resource_name
        FROM campaign
        WHERE campaign.status = 'ENABLED'
    """
    response = ga_service.search(customer_id=cid, query=query)
    campaign_rns = [row.campaign.resource_name for row in response]

    if not campaign_rns:
        return 0

    # Batch pause them all
    campaign_service = client.get_service("CampaignService")
    ops = []
    for rn in campaign_rns:
        op = client.get_type("CampaignOperation")
        campaign = op.update
        campaign.resource_name = rn
        campaign.status = client.enums.CampaignStatusEnum.PAUSED
        from google.protobuf import field_mask_pb2

        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
        ops.append(op)

    campaign_service.mutate_campaigns(customer_id=cid, operations=ops)

    # Audit log
    import uuid as _uuid
    from datetime import datetime
    from typing import cast

    from adcopilot.application.ports.audit_log_repository import AuditLogRepository
    from adcopilot.domain.audit_log import AuditLog, AuditLogId
    from adcopilot.domain.recommendation import RecommendationId

    log = AuditLog(
        id=AuditLogId(str(_uuid.uuid4())),
        recommendation_id=RecommendationId("00000000-0000-0000-0000-000000000000"),
        account_id=account_id_typed,
        kind="PANIC_PAUSE",
        action="EXECUTE",
        payload={
            "campaign_resource_names": campaign_rns,
            "paused_count": len(campaign_rns),
        },
        created_at=datetime.now(UTC),
    )
    await cast(AuditLogRepository, audit_repo).save(log)

    logger.info(
        "panic_pause_complete",
        customer_id=customer_id,
        paused=len(campaign_rns),
    )
    return len(campaign_rns)


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.nightly_db_backup_task",
)
def nightly_db_backup_task() -> dict[str, object]:
    """Create a gzipped pg_dump and upload it to Cloudflare R2.

    Also prunes backup objects older than 30 days to enforce retention.
    Skipped silently when R2 credentials are not configured (e.g. local dev).
    """
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.backup import delete_old_backups, run_backup

    settings = get_settings()
    if not settings.R2_ACCOUNT_ID or not settings.R2_ACCESS_KEY_ID:
        logger.warning("nightly_db_backup.skipped", reason="R2 credentials not configured")
        return {"skipped": True}

    key = run_backup()
    deleted = delete_old_backups(retain_days=30)

    logger.info("nightly_db_backup.done", key=key, deleted_old=deleted)
    return {"key": key, "deleted_old_backups": deleted}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=1,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    name="adcopilot.interfaces.worker.tasks.run_anomaly_detection_task",
)
def run_anomaly_detection_task() -> dict[str, object]:
    """Queue per-account anomaly detection checks — runs every hour at :05.

    Iterates all active accounts, calls AnomalyDetectionUseCase for each,
    and returns an aggregated summary dict.
    """
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()
    return asyncio.run(_run_anomaly_detection_all_accounts(settings))


async def _run_anomaly_detection_all_accounts(settings: object) -> dict[str, object]:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.anomaly.anomaly_detection_use_case import AnomalyDetectionUseCase
    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.alert_repository import SqlAlertRepository
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.hourly_metrics_adapter import (
        GoogleAdsHourlyMetricsAdapter,
    )

    assert isinstance(settings, Settings)
    engine = create_async_engine(settings.DATABASE_URL)

    total_alerts = 0
    total_suppressed = 0
    accounts_checked = 0
    accounts_errored = 0

    try:
        # Fetch all active accounts with OAuth credentials
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(
                session, settings.TOKEN_ENCRYPTION_KEY
            )
            accounts = await account_repo.list_active()
            account_creds: list[tuple[object, str, str]] = []
            for acct in accounts:
                if acct.is_manager:
                    continue
                creds = await credentials_repo.get(AccountId(acct.id))
                if creds is None:
                    continue
                account_creds.append((acct, acct.customer_id, creds.refresh_token))

        metrics_adapter = GoogleAdsHourlyMetricsAdapter(settings)

        for acct, customer_id, refresh_token in account_creds:
            try:
                async with AsyncSession(engine) as session, session.begin():
                    alert_repo = SqlAlertRepository(session)
                    use_case = AnomalyDetectionUseCase(
                        metrics=metrics_adapter,
                        alert_repo=alert_repo,
                    )
                    result = await use_case.execute(
                        AccountId(str(acct.id)),
                        customer_id,
                        refresh_token,
                    )
                total_alerts += result.alerts_created
                total_suppressed += result.alerts_suppressed
                accounts_checked += 1
                logger.info(
                    "anomaly_detection.done",
                    account_id=str(acct.id),
                    alerts_created=result.alerts_created,
                    alerts_suppressed=result.alerts_suppressed,
                )
            except Exception:
                logger.exception("anomaly_detection.failed", account_id=str(acct.id))
                accounts_errored += 1
    finally:
        await engine.dispose()

    logger.info(
        "anomaly_detection.summary",
        accounts_checked=accounts_checked,
        accounts_errored=accounts_errored,
        total_alerts=total_alerts,
        total_suppressed=total_suppressed,
    )
    return {
        "accounts_checked": accounts_checked,
        "accounts_errored": accounts_errored,
        "total_alerts": total_alerts,
        "total_suppressed": total_suppressed,
    }


@celery_app.task(name="adcopilot.interfaces.worker.tasks.check_bidding_upgrade_task")  # type: ignore[untyped-decorator]
def check_bidding_upgrade_task() -> dict[str, object]:
    """Weekly task: check all active accounts for bidding strategy upgrade eligibility."""
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()

    async def _run() -> dict[str, object]:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from adcopilot.application.use_cases.check_bidding_upgrade import CheckBiddingUpgradeUseCase
        from adcopilot.domain.entities import AccountId
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from adcopilot.infrastructure.db.repositories.recommendation_repository import (
            SqlRecommendationRepository,
        )
        from adcopilot.infrastructure.db.repositories.snapshot_repository import (
            SqlSnapshotRepository,
        )

        engine = create_async_engine(settings.DATABASE_URL)
        total_recs = 0
        accounts_checked = 0
        accounts_errored = 0
        try:
            async with AsyncSession(engine) as session:
                account_repo = SqlGoogleAdsAccountRepository(session)
                accounts = await account_repo.list_active()

            for account in accounts:
                try:
                    async with AsyncSession(engine) as session:
                        use_case = CheckBiddingUpgradeUseCase(
                            snapshot_repo=SqlSnapshotRepository(session),
                            rec_repo=SqlRecommendationRepository(session),
                        )
                        recs = await use_case.execute(AccountId(str(account.id)))
                        total_recs += len(recs)
                        accounts_checked += 1
                except Exception:
                    logger.exception(
                        "bidding_upgrade_check.failed", account_id=str(account.id)
                    )
                    accounts_errored += 1
        finally:
            await engine.dispose()

        logger.info(
            "bidding_upgrade_check.summary",
            accounts_checked=accounts_checked,
            accounts_errored=accounts_errored,
            recommendations_created=total_recs,
        )
        return {
            "accounts_checked": accounts_checked,
            "accounts_errored": accounts_errored,
            "recommendations_created": total_recs,
        }

    return asyncio.run(_run())  # type: ignore[return-value]


@celery_app.task(name="adcopilot.interfaces.worker.tasks.check_rlsa_eligibility_task")  # type: ignore[untyped-decorator]
def check_rlsa_eligibility_task() -> dict[str, object]:
    """Weekly task: add RLSA observation audiences to GROWTH-tier accounts with eligible lists."""
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()

    async def _run() -> dict[str, object]:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from adcopilot.application.use_cases.add_rlsa_audiences import AddRlsaAudiencesUseCase
        from adcopilot.domain.entities import AccountId
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
            SqlOAuthCredentialsRepository,
        )
        from adcopilot.infrastructure.google_ads.campaign_writer import CampaignWriter
        from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

        engine = create_async_engine(settings.DATABASE_URL)
        total_added = 0
        accounts_checked = 0
        accounts_errored = 0
        try:
            async with AsyncSession(engine) as session:
                account_repo = SqlGoogleAdsAccountRepository(session)
                credentials_repo = SqlOAuthCredentialsRepository(
                    session, settings.TOKEN_ENCRYPTION_KEY
                )
                accounts = await account_repo.list_active()
                account_creds = []
                for acct in accounts:
                    if acct.is_manager:
                        continue
                    creds = await credentials_repo.get(AccountId(acct.id))
                    if creds is None:
                        continue
                    account_creds.append((acct, acct.customer_id, creds.refresh_token))

            queries_adapter = GoogleAdsQueriesAdapter(settings)
            writer = CampaignWriter(settings)

            for account, customer_id, refresh_token in account_creds:
                try:
                    use_case = AddRlsaAudiencesUseCase(
                        queries_adapter=queries_adapter,
                        campaign_writer=writer,
                    )
                    added = await use_case.execute(
                        account_id=AccountId(str(account.id)),
                        refresh_token=refresh_token,
                        customer_id=customer_id,
                    )
                    total_added += added
                    accounts_checked += 1
                except Exception:
                    logger.exception(
                        "rlsa_eligibility_check.failed", account_id=str(account.id)
                    )
                    accounts_errored += 1
        finally:
            await engine.dispose()

        logger.info(
            "rlsa_eligibility_check.summary",
            accounts_checked=accounts_checked,
            accounts_errored=accounts_errored,
            criteria_created=total_added,
        )
        return {
            "accounts_checked": accounts_checked,
            "accounts_errored": accounts_errored,
            "criteria_created": total_added,
        }

    return asyncio.run(_run())  # type: ignore[return-value]


@celery_app.task(name="adcopilot.interfaces.worker.tasks.check_remarketing_campaign_eligibility_task")  # type: ignore[untyped-decorator]
def check_remarketing_campaign_eligibility_task() -> dict[str, object]:
    """Monthly task: propose Display Remarketing campaigns for eligible GROWTH accounts."""
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()

    async def _run() -> dict[str, object]:
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from adcopilot.application.use_cases.launch.propose_remarketing_campaign import (
            ProposeRemarketingCampaignUseCase,
        )
        from adcopilot.domain.entities import AccountId
        from adcopilot.domain.launch.entities import CampaignBriefId
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
            SqlOAuthCredentialsRepository,
        )
        from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

        engine = create_async_engine(settings.DATABASE_URL)
        proposals_generated = 0
        accounts_checked = 0
        accounts_errored = 0
        try:
            async with AsyncSession(engine) as session:
                account_repo = SqlGoogleAdsAccountRepository(session)
                credentials_repo = SqlOAuthCredentialsRepository(
                    session, settings.TOKEN_ENCRYPTION_KEY
                )
                accounts = await account_repo.list_active()
                account_creds = []
                for acct in accounts:
                    if acct.is_manager:
                        continue
                    creds = await credentials_repo.get(AccountId(acct.id))
                    if creds is None:
                        continue
                    account_creds.append((acct, acct.customer_id, creds.refresh_token))

            queries_adapter = GoogleAdsQueriesAdapter(settings)

            for account, customer_id, refresh_token in account_creds:
                try:
                    use_case = ProposeRemarketingCampaignUseCase(queries_adapter=queries_adapter)
                    proposal = await use_case.execute(
                        account_id=AccountId(str(account.id)),
                        brief_id=CampaignBriefId(""),
                        refresh_token=refresh_token,
                        customer_id=customer_id,
                        search_daily_budget_micros=0,
                    )
                    if proposal is not None:
                        proposals_generated += 1
                        logger.info(
                            "remarketing_proposal_generated_for_account",
                            account_id=str(account.id),
                            proposal_id=proposal.id,
                            budget_micros=proposal.daily_budget_micros,
                        )
                        # TODO: send proposal via Telegram when chat_id is available on account model
                    accounts_checked += 1
                except Exception:
                    logger.exception(
                        "remarketing_eligibility_check.failed", account_id=str(account.id)
                    )
                    accounts_errored += 1
        finally:
            await engine.dispose()

        logger.info(
            "remarketing_eligibility_check.summary",
            accounts_checked=accounts_checked,
            accounts_errored=accounts_errored,
            proposals_generated=proposals_generated,
        )
        return {
            "accounts_checked": accounts_checked,
            "accounts_errored": accounts_errored,
            "proposals_generated": proposals_generated,
        }

    return asyncio.run(_run())  # type: ignore[return-value]


@celery_app.task(
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    name="adcopilot.interfaces.worker.tasks.send_weekly_performance_report_task",
)
def send_weekly_performance_report_task() -> dict[str, object]:
    """Weekly task (Fridays 10:00 UTC): send performance impact summary via Telegram."""
    import asyncio
    from adcopilot.config import get_settings

    settings = get_settings()

    async def _run() -> dict[str, object]:
        # TODO(phase-0.2): wire new performance reporter implementation
        logger.warning("performance_reporter not configured, skipping weekly report")
        return {"skipped": True, "reason": "reporter_not_configured"}

    return asyncio.run(_run())  # type: ignore[return-value]


@celery_app.task(
    max_retries=3,
    default_retry_delay=300,
    autoretry_for=(Exception,),
    name="adcopilot.interfaces.worker.tasks.compare_recommendation_performance_task",
)
def compare_recommendation_performance_task() -> dict[str, object]:
    """Daily task: compare executed recommendations against 7-day and 14-day baselines."""
    import asyncio
    from adcopilot.config import get_settings

    settings = get_settings()

    async def _run() -> dict[str, object]:
        from datetime import UTC, datetime

        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from adcopilot.application.use_cases.compare_recommendation_performance import (
            CompareRecommendationPerformanceUseCase,
        )
        from adcopilot.infrastructure.db.repositories.performance_baseline_repository import (
            SqlPerformanceBaselineRepository,
        )
        from adcopilot.infrastructure.db.repositories.performance_comparison_repository import (
            SqlPerformanceComparisonRepository,
        )
        from adcopilot.infrastructure.db.repositories.recommendation_repository import (
            SqlRecommendationRepository,
        )
        from adcopilot.infrastructure.db.repositories.snapshot_repository import (
            SqlSnapshotRepository,
        )

        engine = create_async_engine(settings.DATABASE_URL)
        try:
            async with AsyncSession(engine) as session:
                rec_repo = SqlRecommendationRepository(session)
                baseline_repo = SqlPerformanceBaselineRepository(session)
                comparison_repo = SqlPerformanceComparisonRepository(session)
                snapshot_repo = SqlSnapshotRepository(session)

                async def _fetch_snapshot(account_id: str, entity_type: str, entity_id: int) -> dict | None:
                    from datetime import date
                    today = date.today()
                    from adcopilot.domain.entities import AccountId
                    campaigns = await snapshot_repo.get_campaigns_by_date(AccountId(account_id), today)
                    if entity_type == "campaign":
                        for c in campaigns:
                            if c.campaign_id == entity_id:
                                return {
                                    "cost_micros": c.cost_micros,
                                    "clicks": c.clicks,
                                    "impressions": c.impressions,
                                    "conversions": c.conversions,
                                }
                    return None

                use_case = CompareRecommendationPerformanceUseCase(
                    rec_repo=rec_repo,
                    baseline_repo=baseline_repo,
                    comparison_repo=comparison_repo,
                    snapshot_fetcher=_fetch_snapshot,
                )
                result = await use_case.run(now=datetime.now(UTC))
                await session.commit()
                return result
        finally:
            await engine.dispose()

    return asyncio.run(_run())  # type: ignore[return-value]


@celery_app.task(name="classify_account_vertical_task")  # type: ignore[misc]
def classify_account_vertical_task(account_id: str) -> dict[str, object]:
    """Classify the vertical of a single account from its latest keyword snapshot."""
    import asyncio as _asyncio

    async def _run() -> dict[str, object]:
        from adcopilot.application.use_cases.classify_account_vertical import (
            ClassifyAccountVerticalUseCase,
        )
        from adcopilot.config import Settings
        from adcopilot.infrastructure.db.engine import build_async_engine
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from sqlalchemy.ext.asyncio import AsyncSession

        settings = Settings()
        engine = build_async_engine(settings)
        try:
            async with AsyncSession(engine) as session:
                account_repo = SqlGoogleAdsAccountRepository(session)
                # Use keyword text from account's latest snapshot if available
                uc = ClassifyAccountVerticalUseCase(account_repo=account_repo)
                vertical = await uc.run(account_id=account_id, keywords=[])
                await session.commit()
                return {"account_id": account_id, "vertical": vertical}
        finally:
            await engine.dispose()

    return _asyncio.run(_run())


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.aggregate_benchmarks_task",
)
def aggregate_benchmarks_task() -> dict[str, object]:
    """Aggregate anonymized performance benchmarks across accounts (weekly)."""
    import asyncio as _asyncio

    async def _run() -> dict[str, object]:
        from adcopilot.application.use_cases.aggregate_benchmarks import (
            AggregateBenchmarksUseCase,
        )
        from adcopilot.config import Settings
        from adcopilot.infrastructure.db.engine import build_async_engine
        from adcopilot.infrastructure.db.repositories.benchmark_repository import (
            SqlBenchmarkRepository,
        )
        from adcopilot.infrastructure.db.repositories.account_summary_provider import (
            SqlAccountSummaryProvider,
        )
        from sqlalchemy.ext.asyncio import AsyncSession

        settings = Settings()
        engine = build_async_engine(settings)
        try:
            async with AsyncSession(engine) as session:
                repo = SqlBenchmarkRepository(session)
                provider = SqlAccountSummaryProvider(session)
                uc = AggregateBenchmarksUseCase(
                    account_summary_provider=provider,
                    benchmark_repo=repo,
                )
                result = await uc.run()
                await session.commit()
                return result
        finally:
            await engine.dispose()

    return _asyncio.run(_run())
