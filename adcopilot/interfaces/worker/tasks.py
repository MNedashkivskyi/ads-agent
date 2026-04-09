"""Celery tasks for snapshot ingestion."""

from __future__ import annotations

import uuid
from datetime import UTC, date

import structlog
from redis import Redis

from adcopilot.application.use_cases.snapshot_account import SnapshotResult
from adcopilot.interfaces.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

_LOCK_TTL_SECONDS = 7200  # 2 hours


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
                credentials_repo=SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY),
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

        async with AsyncSession(engine) as session, session.begin():
            result = await session.execute(
                select(UserModel).where(UserModel.telegram_chat_id.isnot(None))
            )
            users = result.scalars().all()

        notifier = TelegramDigestNotifier(bot_token=settings.TELEGRAM_BOT_TOKEN)

        for user_model in users:
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


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    name="adcopilot.interfaces.worker.tasks.execute_recommendation_task",
)
def execute_recommendation_task(rec_id: str) -> dict[str, object]:
    """Execute a single APPROVED recommendation against the Google Ads API."""
    import asyncio

    return asyncio.run(_run_execute_recommendation(rec_id))


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
                credentials_repo=SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY),
                mutations=GoogleAdsMutationsAdapter(settings),
            )
            result = await use_case.execute(RecommendationId(rec_id))
    finally:
        await engine.dispose()

    logger.info("recommendation executed", rec_id=rec_id)
    return {"rec_id": rec_id, "result": result}
