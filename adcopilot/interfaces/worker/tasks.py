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
            try:
                asyncio.run(_notify_reauth_required(account_id, settings))
            except Exception:
                logger.exception(
                    "failed to send reauth notification after snapshot",
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
    """Send daily recommendation digests to all users with Telegram linked."""
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()
    results = asyncio.run(_run_send_digests(settings))
    logger.info("daily digests sent", **results)
    return results


async def _run_send_digests(settings: object) -> dict[str, object]:
    """Send digests to all Telegram-linked users."""
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
    from adcopilot.infrastructure.telegram.digest_notifier import TelegramDigestNotifier

    assert isinstance(settings, Settings)
    if not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping digests")
        return {"sent": 0, "skipped": 0, "reason": "no_bot_token"}

    today = datetime.now(UTC).date()
    engine = create_async_engine(settings.DATABASE_URL)
    sent = 0
    skipped = 0
    try:
        from sqlalchemy import select

        _INACTIVE_STATUSES = {"past_due", "canceled", "unpaid"}

        async with AsyncSession(engine) as session, session.begin():
            result = await session.execute(
                select(UserModel).where(
                    UserModel.telegram_chat_id.isnot(None),
                    UserModel.notifications_paused.is_(False),
                )
            )
            users = result.scalars().all()

        notifier = TelegramDigestNotifier(bot_token=settings.TELEGRAM_BOT_TOKEN)

        for user_model in users:
            if user_model.subscription_status in _INACTIVE_STATUSES:
                try:
                    from telegram import Bot

                    if user_model.telegram_chat_id is not None:
                        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                        async with bot:
                            await bot.send_message(
                                chat_id=user_model.telegram_chat_id,
                                text=(
                                    "⚠️ Twoja subskrypcja jest nieaktywna. Odwiedź adswise.xyz/app/billing, "
                                    "aby wznowić dostęp."
                                ),
                            )
                except Exception:
                    logger.exception(
                        "failed to send inactive sub warning", user_id=str(user_model.id)
                    )
                skipped += 1
                continue
            try:
                async with AsyncSession(engine) as session, session.begin():
                    account_repo = SqlGoogleAdsAccountRepository(session)
                    rec_repo = SqlRecommendationRepository(session)
                    digest_log_repo = SqlDigestSentLogRepository(session)

                    accounts = await account_repo.list_for_user(UserId(str(user_model.id)))
                    account_ids = [AccountId(a.id) for a in accounts]

                    use_case = SendDailyDigestUseCase(
                        account_repo=account_repo,
                        rec_repo=rec_repo,
                        digest_log_repo=digest_log_repo,
                        notifier=notifier,
                    )
                    digest_result = await use_case.execute(
                        user_id=UserId(str(user_model.id)),
                        telegram_chat_id=user_model.telegram_chat_id,
                        account_ids=account_ids,
                        today=today,
                    )
                if digest_result.sent:
                    sent += 1
                else:
                    skipped += 1
            except Exception:
                logger.exception("digest failed for user", user_id=str(user_model.id))
                skipped += 1
    finally:
        await engine.dispose()

    return {"sent": sent, "skipped": skipped}


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
    if not settings.TELEGRAM_BOT_TOKEN:
        return {"sent": 0, "skipped": 0, "reason": "no_bot_token"}

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
                    UserModel.telegram_chat_id.isnot(None),
                    UserModel.subscription_status == "trialing",
                    UserModel.trial_ends_at.isnot(None),
                    UserModel.trial_ends_at >= reminder_window_start,
                    UserModel.trial_ends_at <= reminder_window_end,
                )
            )
            users = result.scalars().all()

        from telegram import Bot

        for user_model in users:
            if user_model.telegram_chat_id is None:
                skipped += 1
                continue
            try:
                bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                async with bot:
                    await bot.send_message(
                        chat_id=user_model.telegram_chat_id,
                        text=(
                            "⏳ Twój 14-dniowy okres próbny kończy się za 2 dni. "
                            "Odwiedź adswise.xyz/app/billing, aby wybrać plan i kontynuować korzystanie z AdsWise."
                        ),
                    )
                sent += 1
            except Exception:
                logger.exception("trial reminder failed", user_id=str(user_model.id))
                skipped += 1
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
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

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

            if not settings.TELEGRAM_BOT_TOKEN:
                return

            user_repo = SqlUserRepository(session)
            user = await user_repo.get_by_id(account.user_id)
            if user is None or user.telegram_chat_id is None or user.notifications_paused:
                return

            reauth_url = (
                f"{settings.APP_URL.rstrip('/')}/oauth/google/start?account_id={account.id}"
                if settings.APP_URL
                else None
            )
            from adcopilot.infrastructure.telegram.digest_notifier import TelegramDigestNotifier

            notifier = TelegramDigestNotifier(bot_token=settings.TELEGRAM_BOT_TOKEN)
            await notifier.send_reauth_required(
                chat_id=user.telegram_chat_id,
                account_name=account.descriptive_name,
                reauth_url=reauth_url,
            )
    finally:
        await engine.dispose()


async def _notify_reauth_required(account_id: str, settings: object) -> None:
    """Send a reauth notification for an account whose snapshot failed with an auth error.

    The ``needs_reauth`` flag is already set by ``SnapshotAccountUseCase``; this
    helper is responsible only for the Telegram notification.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    assert isinstance(settings, Settings)
    if not settings.TELEGRAM_BOT_TOKEN:
        return

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)
            account = await account_repo.get(AccountId(account_id))
            if account is None:
                return

            user_repo = SqlUserRepository(session)
            user = await user_repo.get_by_id(account.user_id)
            if user is None or user.telegram_chat_id is None or user.notifications_paused:
                return

            reauth_url = (
                f"{settings.APP_URL.rstrip('/')}/oauth/google/start?account_id={account.id}"
                if settings.APP_URL
                else None
            )
            from adcopilot.infrastructure.telegram.digest_notifier import TelegramDigestNotifier

            notifier = TelegramDigestNotifier(bot_token=settings.TELEGRAM_BOT_TOKEN)
            await notifier.send_reauth_required(
                chat_id=user.telegram_chat_id,
                account_name=account.descriptive_name,
                reauth_url=reauth_url,
            )
    finally:
        await engine.dispose()


async def _handle_execution_failure(rec_id: str, error_message: str) -> None:
    """Mark the recommendation FAILED and send a Telegram notification to the user."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.recommendation import RecommendationId, RecommendationStatus
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

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

            if not settings.TELEGRAM_BOT_TOKEN:
                return

            account_repo = SqlGoogleAdsAccountRepository(session)
            account = await account_repo.get(rec.account_id)
            if account is None:
                return

            user_repo = SqlUserRepository(session)
            user = await user_repo.get_by_id(account.user_id)
            if user is None or user.telegram_chat_id is None or user.notifications_paused:
                return

            from adcopilot.infrastructure.telegram.digest_notifier import TelegramDigestNotifier

            notifier = TelegramDigestNotifier(bot_token=settings.TELEGRAM_BOT_TOKEN)
            await notifier.send_execution_failed(
                chat_id=user.telegram_chat_id,
                recommendation=rec,
                error_message=error_message,
            )
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
    telegram_chat_id: int | None = None,
) -> dict[str, object]:
    """Generate a campaign proposal and notify the user via Telegram.

    Dispatched when the user clicks "🚀 Generate my campaign" in the interview
    summary, or when they submit revision text after clicking "✏️ Make changes".
    """
    import asyncio

    return asyncio.run(_run_generate_campaign(brief_id, revision_text, telegram_chat_id))


async def _run_generate_campaign(
    brief_id: str,
    revision_text: str | None,
    telegram_chat_id: int | None,
) -> dict[str, object]:
    """Run the proposal-generation pipeline and notify the user."""
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
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
    from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator
    from adcopilot.infrastructure.telegram.proposal_handler import (
        format_proposal_summary,
        proposal_action_keyboard,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    chat_id = telegram_chat_id
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

            # Resolve Telegram chat_id from user record if not provided
            if chat_id is None:
                user_repo = SqlUserRepository(session)
                user = await user_repo.get_by_id(brief.user_id)
                chat_id = user.telegram_chat_id if user else None

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

    if not settings.TELEGRAM_BOT_TOKEN or chat_id is None:
        return {"proposal_id": proposal_id, "error": error_text}

    from telegram import Bot

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    async with bot:
        if error_text:
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "⚠️ I ran into an issue generating your proposal. "
                    "Please try again with /launch or contact support."
                ),
            )
        else:
            # Re-load proposal for summary (outside the closed session)
            engine2 = create_async_engine(settings.DATABASE_URL)
            try:
                async with AsyncSession(engine2) as session2:
                    from adcopilot.domain.launch.entities import CampaignProposalId

                    proposal_repo2 = SqlCampaignProposalRepository(session2)
                    proposal_obj = await proposal_repo2.get(CampaignProposalId(proposal_id))  # type: ignore[arg-type]
            finally:
                await engine2.dispose()

            if proposal_obj is None:
                return {"error": "proposal_not_found_after_save"}

            summary = format_proposal_summary(proposal_obj)
            keyboard = proposal_action_keyboard(
                proposal_id=str(proposal_obj.id),
                brief_id=brief_id,
                app_url=settings.APP_URL,
            )
            await bot.send_message(
                chat_id=chat_id,
                text=summary,
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    return {"proposal_id": proposal_id}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.create_campaign_task",
)
def create_campaign_task(brief_id: str, telegram_chat_id: int) -> dict[str, object]:
    """Create the full campaign in Google Ads (PAUSED) and notify user.

    Dispatched when the user confirms "✅ Launch this campaign".
    """
    import asyncio

    return asyncio.run(_run_create_campaign(brief_id, telegram_chat_id))


async def _run_create_campaign(brief_id: str, telegram_chat_id: int) -> dict[str, object]:
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
    from adcopilot.infrastructure.telegram.proposal_handler import post_launch_keyboard

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    error_text: str | None = None
    campaign_rn: str | None = None

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

            writer = CampaignWriter(
                settings=settings,
                audit_log_repo=audit_repo,
                account_id=AccountId(account.id),
            )

            # Track all created resources for potential rollback
            ad_rns: list[str] = []
            kw_rns: list[str] = []
            neg_rns: list[str] = []
            ag_rns: list[str] = []

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

                neg_rns = await writer.create_negative_keywords(
                    account.customer_id,
                    credentials.refresh_token,
                    campaign_rn,
                    proposal.negative_keywords,
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
                if campaign_rn or ag_rns or kw_rns or ad_rns or neg_rns:
                    resources = CreatedCampaignResources(
                        campaign_resource_name=campaign_rn or "",
                        budget_resource_name=budget_rn if "budget_rn" in dir() else "",
                        ad_group_resource_names=ag_rns,
                        keyword_resource_names=kw_rns,
                        ad_resource_names=ad_rns,
                        negative_resource_names=neg_rns,
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

    if not settings.TELEGRAM_BOT_TOKEN:
        return {"campaign_rn": campaign_rn, "error": error_text}

    from telegram import Bot

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    async with bot:
        if error_text:
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=(
                    "⚠️ Failed to create your campaign in Google Ads.\n\n"
                    f"Error: {error_text}\n\n"
                    "Please try again or contact support."
                ),
            )
        else:
            keyboard = post_launch_keyboard(brief_id)
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=(
                    "✅ *Campaigns created and paused.*\n\n"
                    "Your campaign is ready in Google Ads but not yet spending.\n\n"
                    "Tap *Enable and go live* when you're ready to start serving ads, "
                    "or *Don't enable yet* to review it first."
                ),
                reply_markup=keyboard,
                parse_mode="Markdown",
            )

    return {"campaign_rn": campaign_rn}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=2,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    name="adcopilot.interfaces.worker.tasks.enable_campaign_task",
)
def enable_campaign_task(brief_id: str, telegram_chat_id: int) -> dict[str, object]:
    """Enable the paused campaign (second explicit confirmation) and start monitoring.

    Dispatched when the user clicks "🚀 Enable and go live".
    """
    import asyncio

    return asyncio.run(_run_enable_campaign(brief_id, telegram_chat_id))


async def _run_enable_campaign(brief_id: str, telegram_chat_id: int) -> dict[str, object]:
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

    if not settings.TELEGRAM_BOT_TOKEN:
        return {"error": error_text}

    from telegram import Bot

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    async with bot:
        if error_text:
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=(
                    "⚠️ Failed to enable your campaign.\n\n"
                    f"Error: {error_text}\n\n"
                    "Please try again or contact support."
                ),
            )
        else:
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=(
                    "🚀 *You're live!*\n\n"
                    "I'll monitor this campaign closely for the first 48 hours "
                    "and alert you immediately if anything unusual is detected."
                ),
                parse_mode="Markdown",
            )

    # Schedule 48-hour high-alert monitoring (hourly checks)
    if not error_text and account_id_str:
        monitor_new_campaign_task.apply_async(
            args=[brief_id, account_id_str, 1, telegram_chat_id],
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
    telegram_chat_id: int,
) -> dict[str, object]:
    """Run anomaly detection for a newly-enabled campaign, hourly for 48 hours.

    Sends high-alert Telegram messages if new issues are detected.
    After 48 hours the monitoring window closes and nightly digests take over.
    """
    import asyncio

    return asyncio.run(
        _run_monitor_new_campaign(brief_id, account_id, hours_elapsed, telegram_chat_id)
    )


async def _run_monitor_new_campaign(
    brief_id: str,
    account_id: str,
    hours_elapsed: int,
    telegram_chat_id: int,
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
    from adcopilot.infrastructure.telegram.proposal_handler import panic_pause_keyboard

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

            if new_recs and settings.TELEGRAM_BOT_TOKEN:
                from telegram import Bot

                bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
                async with bot:
                    for rec in new_recs:
                        kind_label = rec.kind.replace("_", " ").title()
                        savings_pln = rec.estimated_monthly_savings_micros / 1_000_000
                        alert_text = (
                            f"⚠️ *Early alert — {kind_label}*\n\n"
                            f"Potential issue detected in your new campaign.\n"
                            f"Est. impact: {savings_pln:,.2f} PLN/month\n\n"
                            f"Review at /app to take action."
                        )
                        keyboard = panic_pause_keyboard(account_id)
                        await bot.send_message(
                            chat_id=telegram_chat_id,
                            text=alert_text,
                            reply_markup=keyboard,
                            parse_mode="Markdown",
                        )
                        alerts_sent += 1
    finally:
        await engine2.dispose()

    # Schedule next check if still within the 48-hour window
    if hours_elapsed < _MONITORING_WINDOW_HOURS:
        monitor_new_campaign_task.apply_async(
            args=[brief_id, account_id, hours_elapsed + 1, telegram_chat_id],
            countdown=_MONITORING_INTERVAL_SECONDS,
        )
        logger.info(
            "next monitoring check scheduled",
            brief_id=brief_id,
            hours_elapsed=hours_elapsed + 1,
        )
    else:
        # 48-hour window complete — revert to standard daily digest
        if settings.TELEGRAM_BOT_TOKEN:
            from telegram import Bot

            bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
            async with bot:
                await bot.send_message(
                    chat_id=telegram_chat_id,
                    text=(
                        "✅ *48-hour monitoring window complete.*\n\n"
                        "Your campaign is now covered by the standard daily digest. "
                        "I'll keep optimising and report any issues each morning."
                    ),
                    parse_mode="Markdown",
                )
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
def panic_pause_campaigns_task(account_id: str, telegram_chat_id: int) -> dict[str, object]:
    """Pause all ENABLED campaigns in *account_id* immediately.

    Dispatched by /panic command or the [🛑 Pause everything now] button.
    Target: complete within 30 seconds.
    """
    import asyncio

    return asyncio.run(_run_panic_pause(account_id, telegram_chat_id))


async def _run_panic_pause(account_id: str, telegram_chat_id: int) -> dict[str, object]:
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

    if not settings.TELEGRAM_BOT_TOKEN:
        return {"paused": paused_count, "error": error_text}

    from telegram import Bot

    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    async with bot:
        if error_text:
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=(
                    f"⚠️ Panic pause encountered an error: {error_text}\n\n"
                    "Please check Google Ads directly to verify campaign statuses."
                ),
            )
        elif paused_count == 0:
            await bot.send_message(
                chat_id=telegram_chat_id,
                text="No enabled campaigns found to pause in this account.",
            )
        else:
            await bot.send_message(
                chat_id=telegram_chat_id,
                text=(
                    f"🛑 *Done. {paused_count} campaign(s) paused.*\n\n"
                    "All campaigns in this account are now paused and no longer spending. "
                    "Use /launch to manage or re-enable them."
                ),
                parse_mode="Markdown",
            )

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
