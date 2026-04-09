"""Celery tasks for snapshot ingestion."""

from __future__ import annotations

import uuid
from datetime import date

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

            rec_repo = SqlRecommendationRepository(session)
            rule_engine = build_rule_engine(rec_repo)
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
