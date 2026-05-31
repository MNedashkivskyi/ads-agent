"""Celery tasks for snapshot ingestion, campaign launch, and monitoring."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import structlog
from redis import Redis

from adcopilot.application.use_cases.snapshot_account import SnapshotResult
from adcopilot.interfaces.worker.celery_app import celery_app

logger = structlog.get_logger(__name__)

_PLAN_ACCOUNT_LIMITS: dict[str, int] = {"starter": 1, "growth": 3, "pro": 10}
_OAUTH_PENDING_KEY_PREFIX = "oauth_pending:"

_LOCK_TTL_SECONDS = 7200  # 2 hours
_MONITORING_INTERVAL_SECONDS = 3600  # 1 hour
_MONITORING_WINDOW_HOURS = 48


def _redis_client() -> Redis:  # type: ignore[type-arg]
    from adcopilot.config import get_settings

    settings = get_settings()
    return Redis.from_url(settings.REDIS_URL)


# ---------------------------------------------------------------------------
# Google Ads account-linking task (dispatched from the OAuth callback so the
# blocking gRPC calls never touch the FastAPI event loop).
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.link_google_ads_accounts_task",
    max_retries=2,
    default_retry_delay=30,
)
def link_google_ads_accounts_task(user_id: str) -> dict[str, object]:
    """Fetch Google Ads customer IDs and persist accounts after OAuth consent.

    The refresh token is read from a temporary encrypted Redis entry written
    by the OAuth callback.  After processing, the entry is deleted regardless
    of outcome so it cannot be replayed.
    """
    import asyncio

    from adcopilot.config import get_settings

    settings = get_settings()
    try:
        return asyncio.run(_async_link_google_ads_accounts(settings, user_id))
    except Exception as exc:
        logger.error(
            "link_google_ads_accounts_task failed",
            user_id=user_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return {"success": False, "error": str(exc)}


async def _async_link_google_ads_accounts(
    settings: object,
    user_id: str,
) -> dict[str, object]:
    """Async implementation of account linking — runs inside asyncio.run()."""
    import base64
    import hashlib
    import json

    from cryptography.fernet import Fernet
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId, GoogleAdsAccount, OAuthCredentials, UserId
    from adcopilot.domain.exceptions import GoogleAdsTokenNotApproved
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
    from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter

    assert isinstance(settings, Settings)

    # --- decrypt pending token from Redis ---
    redis = _redis_client()
    pending_key = f"{_OAUTH_PENDING_KEY_PREFIX}{user_id}"
    enc_data = redis.get(pending_key)
    if not enc_data:
        logger.warning("no pending oauth token found", user_id=user_id)
        return {"success": False, "error": "no_pending_token"}

    fernet_key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.TOKEN_ENCRYPTION_KEY.encode()).digest()
    )
    fernet = Fernet(fernet_key)
    raw = json.loads(fernet.decrypt(enc_data).decode())
    refresh_token: str = raw["refresh_token"]
    access_token: str | None = raw.get("access_token")
    expires_at_iso: str | None = raw.get("expires_at")
    expires_at: datetime | None = datetime.fromisoformat(expires_at_iso) if expires_at_iso else None

    # --- open DB session ---
    engine = create_async_engine(settings.DATABASE_URL)
    linked_ids: list[str] = []
    try:
        async with AsyncSession(engine) as session:
            user_repo = SqlUserRepository(session)
            acc_repo = SqlGoogleAdsAccountRepository(session)
            creds_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)

            user = await user_repo.get_by_id(UserId(user_id))
            if user is None:
                logger.error("user not found in oauth linking task", user_id=user_id)
                redis.delete(pending_key)
                return {"success": False, "error": "user_not_found"}

            existing_accounts = await acc_repo.list_for_user(UserId(user_id))
            account_limit = _PLAN_ACCOUNT_LIMITS.get(user.plan.value, 1)
            slots_remaining = account_limit - len(existing_accounts)
            if slots_remaining <= 0:
                logger.warning(
                    "account limit reached in oauth linking task",
                    user_id=user_id,
                    plan=user.plan.value,
                )
                redis.delete(pending_key)
                return {"success": False, "error": "account_limit_reached"}

            # --- call Google Ads API (runs in a thread pool inside asyncio.run) ---
            ads_client = GoogleAdsClientAdapter(settings)
            try:
                resource_names = await ads_client.list_accessible_customers(refresh_token)
                customer_ids = [rn.split("/")[-1] for rn in resource_names]
            except GoogleAdsTokenNotApproved as exc:
                logger.error("developer token not approved", error=str(exc))
                redis.delete(pending_key)
                return {"success": False, "error": "token_not_approved"}
            except Exception as exc:
                logger.error("failed to list google ads customers", error=str(exc))
                redis.delete(pending_key)
                return {"success": False, "error": str(exc)}

            for customer_id in customer_ids[:slots_remaining]:
                account_id = AccountId(
                    str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}/{customer_id}"))
                )
                descriptive_name = ""
                currency = ""
                timezone = ""
                is_manager = False
                try:
                    info = await ads_client.get_customer_info(refresh_token, customer_id)
                    descriptive_name = info.descriptive_name
                    currency = info.currency
                    timezone = info.timezone
                    is_manager = info.is_manager
                except Exception as exc:
                    logger.warning(
                        "failed to fetch customer info — saving with defaults",
                        customer_id=customer_id,
                        error=str(exc),
                    )

                account = GoogleAdsAccount(
                    id=account_id,
                    user_id=UserId(user_id),
                    customer_id=customer_id,
                    descriptive_name=descriptive_name,
                    currency=currency,
                    timezone=timezone,
                    is_manager=is_manager,
                    write_enabled=not is_manager,
                    connected_at=datetime.now(UTC),
                )
                await acc_repo.save(account)

                creds = OAuthCredentials(
                    account_id=account_id,
                    refresh_token=refresh_token,
                    access_token=access_token,
                    expires_at=expires_at,
                )
                await creds_repo.save(creds)
                linked_ids.append(customer_id)

            await session.commit()
    finally:
        await engine.dispose()
        redis.delete(pending_key)

    logger.info(
        "google ads accounts linked via celery task",
        user_id=user_id,
        linked_count=len(linked_ids),
    )

    # Kick off an initial snapshot for each newly linked account so the user
    # sees data immediately instead of waiting for the 3 AM nightly run.
    today_iso = date.today().isoformat()
    redis = _redis_client()
    now_iso = datetime.now(UTC).isoformat()
    for customer_id in linked_ids:
        account_id = str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}/{customer_id}")
        )
        # Mark the account as "initial sync in progress" in Redis.
        # TTL of 10 min — if the task hangs, the marker auto-expires so the
        # frontend doesn't show "syncing" forever.
        redis.set(
            f"sync:initial:{account_id}",
            now_iso,
            ex=600,
        )
        snapshot_account_task.delay(account_id, today_iso)
        logger.info(
            "queued initial snapshot after account linking",
            account_id=account_id,
            user_id=user_id,
        )

    return {"success": True, "linked_count": len(linked_ids), "linked_ids": linked_ids}


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
            logger.warning(
                "snapshot auth failure — user needs to reconnect Google Ads",
                account_id=account_id,
            )
        if not result.success:
            # Store the error so the sync-status endpoint can report it.
            redis.set(
                f"sync:error:{account_id}",
                result.error_message or "Unknown error",
                ex=3600,  # 1 hour TTL
            )
        if result.success:
            # Clear any stale error from a previous failed attempt.
            redis.delete(f"sync:error:{account_id}")
            # Run detection asynchronously after a successful snapshot
            asyncio.run(_run_detection(settings, AccountId(account_id), snap_date))
            # Record QS history for trend tracking
            asyncio.run(_record_qs_history(settings, account_id, snap_date))
            # Pull GA4 metrics if credentials are configured
            snapshot_ga4_data_task.delay(account_id, snap_date.isoformat())
            snapshot_auction_insights_task.delay(account_id, snap_date.isoformat())
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
    except Exception as exc:
        # Unexpected crash (e.g. all 14 queries failed) — save error for frontend.
        redis.set(
            f"sync:error:{account_id}",
            str(exc)[:500],
            ex=3600,
        )
        raise
    finally:
        redis.delete(lock_key)
        # Clear the initial-sync marker so the frontend stops showing
        # the progress bar.  This runs whether the snapshot succeeded or
        # failed — either way, the sync attempt is finished.
        redis.delete(f"sync:initial:{account_id}")


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

            # Check if conversion tracking is working — load conversion actions
            # from the snapshot repository to determine if any are healthy.
            snapshot_repo = SqlSnapshotRepository(session)
            conversion_actions = await snapshot_repo.get_conversion_actions(
                AccountId(str(account_id)), snap_date
            )
            has_working_tracking = any(
                a.status == "ENABLED" and a.all_conversions > 0 for a in conversion_actions
            )
            if not has_working_tracking:
                logger.info(
                    "detection.conversion_tracking_missing — skipping conversion-dependent rules",
                    account_id=str(account_id),
                )

            rule_engine = build_rule_engine(
                rec_repo, snooze_repo, has_working_tracking=has_working_tracking
            )
            use_case = RunDetectionUseCase(
                snapshot_repo=snapshot_repo,
                rec_repo=rec_repo,
                rule_engine=rule_engine,
                account_repo=SqlGoogleAdsAccountRepository(session),
            )
            await use_case.execute(AccountId(str(account_id)), snap_date)
            await _generate_explanations(session, settings, AccountId(str(account_id)))
            await _update_experiment_metrics(session, settings, AccountId(str(account_id)))
            await _notify_pmax_alerts(session, settings, AccountId(str(account_id)), snap_date)
    except Exception:
        logger.exception("detection failed (non-fatal)", account_id=str(account_id))
    finally:
        await engine.dispose()


async def _generate_explanations(
    session: object,
    settings: object,
    account_id: object,
) -> None:
    """Generate LLM explanations for all PENDING recs that lack one."""
    from sqlalchemy.ext.asyncio import AsyncSession

    from adcopilot.application.use_cases.explain_recommendation import ExplainRecommendationUseCase
    from adcopilot.config import Settings
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

    assert isinstance(settings, Settings)
    assert isinstance(session, AsyncSession)

    rec_repo = SqlRecommendationRepository(session)
    pending = await rec_repo.list_pending(str(account_id))
    unexplained = [r for r in pending if not r.explanation]
    if not unexplained:
        return

    if not settings.LLM_API_KEY:
        logger.warning("LLM_API_KEY not set — skipping explanation generation")
        return
    llm = AnthropicClient(api_key=settings.LLM_API_KEY)
    try:
        use_case = ExplainRecommendationUseCase(llm=llm, repo=rec_repo)

        explained = 0
        for rec in unexplained:
            try:
                await use_case.execute(rec.id, language="pl")
                explained += 1
            except Exception:
                logger.warning("explain_recommendation_failed", rec_id=str(rec.id))

        logger.info(
            "explanations generated",
            account_id=str(account_id),
            total=len(unexplained),
            explained=explained,
        )
    finally:
        await llm.aclose()


async def _record_qs_history(settings: object, account_id: str, snap_date: date) -> None:
    """Upsert daily QS values into keyword_qs_history for trend tracking."""
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.record_qs_history import record_qs_history
    from adcopilot.config import Settings

    assert isinstance(settings, Settings)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await record_qs_history(account_id, snap_date, session)
    except Exception as exc:
        logger.warning("record_qs_history_failed", account_id=account_id, error=str(exc))
    finally:
        await engine.dispose()


async def _update_experiment_metrics(
    session: object,
    settings: object,
    account_id: object,
) -> None:
    """Update per-ad metrics for running experiments and conclude if significant."""
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from adcopilot.application.use_cases.evaluate_experiment import evaluate_experiment
    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.ad_experiment_repository import (
        AdExperimentRepository,
    )
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.mutations_adapter import GoogleAdsMutationsAdapter
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    assert isinstance(settings, Settings)
    assert isinstance(session, AsyncSession)

    acct_id = AccountId(str(account_id))

    account_repo = SqlGoogleAdsAccountRepository(session)
    credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
    exp_repo = AdExperimentRepository(session)

    accounts = await account_repo.get(acct_id)
    if accounts is None:
        return
    credentials = await credentials_repo.get(acct_id)
    if credentials is None:
        return

    running = await exp_repo.list_running(str(account_id))
    if not running:
        return

    google_ads = GoogleAdsQueriesAdapter(settings)
    mutations = GoogleAdsMutationsAdapter(settings)

    for exp in running:
        try:
            ctrl_metrics = await google_ads.fetch_ad_metrics(
                credentials.refresh_token,
                accounts.customer_id,
                exp.control_ad_resource_name,
            )
            var_metrics = await google_ads.fetch_ad_metrics(
                credentials.refresh_token,
                accounts.customer_id,
                exp.variant_ad_resource_name,
            )
            await exp_repo.update_metrics(str(exp.id), ctrl_metrics, var_metrics)

            result = evaluate_experiment(
                control_metrics=ctrl_metrics,
                variant_metrics=var_metrics,
                min_impressions=exp.min_impressions,
                confidence_threshold=exp.confidence_threshold,
                started_at=exp.started_at,
            )

            if result.should_conclude:
                now = datetime.now(UTC)
                await exp_repo.conclude(str(exp.id), result.winner, now)

                # Pause losing ad
                ad_group_id = int(exp.ad_group_resource_name.split("/")[-1])
                loser_rn = (
                    exp.variant_ad_resource_name
                    if result.winner == "control"
                    else exp.control_ad_resource_name
                )
                loser_ad_id = int(loser_rn.split("~")[-1])
                try:
                    await mutations.pause_ad(
                        refresh_token=credentials.refresh_token,
                        customer_id=accounts.customer_id,
                        ad_group_id=ad_group_id,
                        ad_id=loser_ad_id,
                    )
                except Exception as pause_exc:
                    logger.warning("experiment.pause_loser_failed", error=str(pause_exc))

                logger.info(
                    "experiment.concluded",
                    experiment_id=str(exp.id),
                    winner=result.winner,
                    reason=result.reason,
                )
        except Exception as exc:
            logger.warning(
                "experiment.metrics_update_failed", experiment_id=str(exp.id), error=str(exc)
            )


async def _notify_pmax_alerts(
    session: object,
    settings: object,
    account_id: object,
    snap_date: date,
) -> None:
    """Send WebNotifier alerts for freshly-detected PMax anomalies."""
    import uuid as _uuid_mod
    from datetime import datetime

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession

    from adcopilot.domain.recommendation import RecommendationKind, RecommendationStatus
    from adcopilot.infrastructure.db.models import RecommendationModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
    from adcopilot.infrastructure.notifications.web_notifier_adapter import SqlWebNotifier

    _PMAX_KINDS = {
        RecommendationKind.PMAX_LOW_ROAS.value,
        RecommendationKind.PMAX_ASSET_DISAPPROVED.value,
    }

    from adcopilot.config import Settings

    assert isinstance(settings, Settings)
    assert isinstance(session, AsyncSession)

    today = datetime.now(tz=UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    acct_uuid = _uuid_mod.UUID(str(account_id))

    result = await session.execute(
        select(RecommendationModel).where(
            RecommendationModel.account_id == acct_uuid,
            RecommendationModel.kind.in_(_PMAX_KINDS),
            RecommendationModel.status == RecommendationStatus.PENDING.value,
            RecommendationModel.created_at >= today,
        )
    )
    pmax_recs = result.scalars().all()
    if not pmax_recs:
        return

    account_repo = SqlGoogleAdsAccountRepository(session)
    account = await account_repo.get(account_id)
    if account is None:
        return

    user_repo = SqlUserRepository(session)
    user = await user_repo.get(account.user_id)
    if user is None:
        return

    notifier = SqlWebNotifier(session)

    _TITLES = {
        RecommendationKind.PMAX_LOW_ROAS.value: "Niski ROAS kampanii Performance Max",
        RecommendationKind.PMAX_ASSET_DISAPPROVED.value: "Odrzucone zasoby kampanii Performance Max",
    }
    _BODIES = {
        RecommendationKind.PMAX_LOW_ROAS.value: (
            "Twoja kampania Performance Max ma niski zwrot z wydatków reklamowych (ROAS). "
            "Sprawdź ustawienia grupy zasobów i stawki konwersji."
        ),
        RecommendationKind.PMAX_ASSET_DISAPPROVED.value: (
            "Zasoby w Twojej kampanii Performance Max mogły zostać odrzucone przez Google. "
            "Wejdź w Google Ads i sprawdź status zasobów w grupie zasobów."
        ),
    }

    for rec in pmax_recs:
        await notifier.send_alert(
            user_id=str(user.id),
            title=_TITLES.get(rec.kind, "Alert PMax"),
            body=_BODIES.get(rec.kind, "Wykryto anomalię w kampanii Performance Max."),
            metadata={
                "recommendation_id": str(rec.id),
                "account_id": str(account_id),
                "kind": rec.kind,
            },
        )
    logger.info("pmax_alerts.sent", count=len(pmax_recs), account_id=str(account_id))


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
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import Settings
    from adcopilot.infrastructure.db.models import UserModel

    assert isinstance(settings, Settings)

    engine = create_async_engine(settings.DATABASE_URL)
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
def execute_recommendation_task(
    self: object, rec_id: str, options: dict | None = None
) -> dict[str, object]:
    """Execute a single APPROVED recommendation against the Google Ads API.

    Auth errors (revoked/expired refresh token) are caught immediately and
    treated as permanent failures — retrying with the same bad token is
    pointless.  For all other exceptions the task retries up to max_retries
    times with exponential back-off; after the final retry the recommendation
    is marked FAILED and the user receives a Telegram notification.
    """
    import asyncio

    from celery import Task  # type: ignore[import-untyped]

    from adcopilot.domain.exceptions import CampaignNotFoundError, GoogleAdsAuthError

    assert isinstance(self, Task)
    try:
        return asyncio.run(_run_execute_recommendation(rec_id))
    except GoogleAdsAuthError as exc:
        # Expected, terminal condition: the user's Google OAuth token expired or
        # was revoked. Retrying can't help — mark the rec FAILED and flag the
        # account needs_reauth (so the UI can prompt a reconnect), then finish
        # the task cleanly. Re-raising would log a misleading "task raised
        # unexpected" traceback and trip the task_failure → Sentry path.
        logger.warning(
            "recommendation needs reauth — token expired/revoked",
            rec_id=rec_id,
            error=str(exc),
        )
        try:
            asyncio.run(_handle_auth_failure(rec_id))
        except Exception:
            logger.exception("failed to handle auth failure", rec_id=rec_id)
        return {"rec_id": rec_id, "status": "failed", "reason": "needs_reauth"}
    except CampaignNotFoundError as exc:
        # Expected, terminal business condition: the recommendation is stale and
        # the campaign was removed in Google Ads. There is nothing to retry, so
        # mark it (and any siblings targeting the same removed campaign) EXPIRED
        # and finish the task cleanly. Re-raising would log a misleading "task
        # raised unexpected" traceback and trip the task_failure → Sentry path.
        logger.warning(
            "recommendation expired — campaign removed", rec_id=rec_id, error=str(exc)
        )
        expired = 0
        try:
            expired = asyncio.run(_expire_recs_for_removed_campaign(rec_id))
        except Exception:
            logger.exception("failed to expire recs for removed campaign", rec_id=rec_id)
        return {"rec_id": rec_id, "status": "expired", "reason": str(exc), "expired": expired}
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


async def _expire_recs_for_removed_campaign(rec_id: str) -> int:
    """Expire a stale rec (and siblings) whose target campaign was removed.

    Returns the number of recommendations expired. Keeping the list "actual"
    this way avoids re-running full detection just to drop dead suggestions.
    """
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
                logger.error("recommendation not found during expiry", rec_id=rec_id)
                return 0

            campaign_id = rec.target.get("campaign_id")
            if campaign_id is None:
                # No campaign target — just expire this one rec.
                await rec_repo.update_status(
                    RecommendationId(rec_id), RecommendationStatus.EXPIRED
                )
                return 1

            expired = await rec_repo.expire_open_for_campaign(rec.account_id, int(campaign_id))
            logger.info(
                "expired recommendations for removed campaign",
                rec_id=rec_id,
                campaign_id=campaign_id,
                expired=expired,
            )
            return expired
    finally:
        await engine.dispose()


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=0,
    name="adcopilot.interfaces.worker.tasks.generate_campaign_task",
    soft_time_limit=110,
    time_limit=120,
)
def generate_campaign_task(
    brief_id: str,
    revision_text: str | None = None,
    template_id: str | None = None,
) -> dict[str, object]:
    """Generate a campaign proposal (log-only; notification wired in Phase 1).

    Dispatched when the user submits a campaign brief or revision.
    template_id: when set, uses hybrid path (template structure + LLM copy).
    """
    import asyncio

    return asyncio.run(_run_generate_campaign(brief_id, revision_text, template_id))


async def _run_generate_campaign(
    brief_id: str,
    revision_text: str | None,
    template_id: str | None = None,
) -> dict[str, object]:
    """Run the proposal-generation pipeline.

    The operation is split into **three short DB interactions** so that no
    database connection is held open during the slow LLM calls.  Holding a
    long-running transaction open while waiting for LLM responses causes
    Railway's managed PostgreSQL to kill the idle-in-transaction connection
    (~30 s timeout), which silently prevents the brief status from ever
    transitioning to PROPOSED.

    Flow
    ----
    1. Short read-tx  \u2014 load the brief; bail out early on missing/invalid.
    2. LLM pipeline   \u2014 no DB connection held at all (can take 1\u20133 minutes).
    3. Short write-tx \u2014 save the proposal and mark the brief PROPOSED.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.launch.generate_proposal import (
        GenerateCampaignProposalUseCase,
    )
    from adcopilot.config import get_settings
    from adcopilot.domain.launch.entities import CampaignBriefId, LaunchStatus
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
        SqlCampaignProposalRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    proposal_id: str | None = None
    error_text: str | None = None

    try:
        # \u2500\u2500 Step 1: load brief (short tx, connection released immediately) \u2500\u2500
        async with AsyncSession(engine) as session, session.begin():
            brief_repo = SqlCampaignBriefRepository(session)
            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None:
                logger.error("generate_campaign_task: brief not found", brief_id=brief_id)
                return {"error": "brief_not_found"}
        # session and DB connection are fully released here;
        # nothing is held open during the LLM calls below.

        if not settings.LLM_API_KEY:
            # Template-only path (fast, no LLM calls, no idle-connection risk)
            from adcopilot.domain.launch.templates import build_proposal_from_template

            proposal = build_proposal_from_template(brief)
            logger.info(
                "proposal_generation_succeeded",
                brief_id=brief.id,
                proposal_id=proposal.id,
                via="template_no_llm",
            )
        else:
            # \u2500\u2500 Step 2: LLM pipeline \u2014 no DB connection held \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
            from adcopilot.application.services.template_proposal_assembler import (
                TemplateProposalAssembler,
            )
            from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
            from adcopilot.infrastructure.llm.campaign_generator import CampaignGenerator
            from adcopilot.infrastructure.vertical_templates.yaml_adapter import (
                YamlVerticalTemplateAdapter,
            )

            llm = AnthropicClient(api_key=settings.LLM_API_KEY)
            try:
                generator = CampaignGenerator(llm)
                use_case = GenerateCampaignProposalUseCase(
                    brief_repo=None,     # not needed for content-only generation
                    proposal_repo=None,  # not needed for content-only generation
                    generator=generator,
                    template_repo=YamlVerticalTemplateAdapter(),
                    assembler=TemplateProposalAssembler(),
                )
                # generate_content_only runs the full LLM pipeline (vertical
                # detection -> structure -> ad copy -> negatives -> extensions ->
                # brand) plus validation, retry, and template-fallback, but does
                # NOT touch the DB at all.
                proposal = await use_case.generate_content_only(
                    brief,
                    revision_feedback=revision_text,
                    template_id=template_id,
                )
            finally:
                await llm.aclose()

        # \u2500\u2500 Step 3: persist proposal + mark brief PROPOSED (short write-tx) \u2500\u2500
        async with AsyncSession(engine) as session, session.begin():
            proposal_repo = SqlCampaignProposalRepository(session)
            brief_repo_w = SqlCampaignBriefRepository(session)
            await proposal_repo.save(proposal)
            await brief_repo_w.update_status(brief.id, LaunchStatus.PROPOSED)

        proposal_id = str(proposal.id)

    except Exception as exc:
        logger.exception("generate_campaign_task failed", brief_id=brief_id)
        error_text = str(exc)[:200]
        try:
            async with AsyncSession(engine) as session, session.begin():
                brief_repo_f = SqlCampaignBriefRepository(session)
                await brief_repo_f.update_status(
                    CampaignBriefId(brief_id), LaunchStatus.FAILED
                )
        except Exception:
            logger.exception(
                "generate_campaign_task: failed to mark brief as FAILED",
                brief_id=brief_id,
            )
    finally:
        await engine.dispose()

    # TODO(phase-0.2): send proposal notification via new notifier
    return {"proposal_id": proposal_id, "error": error_text}


@celery_app.task(  # type: ignore[untyped-decorator]
    max_retries=1,
    default_retry_delay=10,
    autoretry_for=(Exception,),
    name="adcopilot.interfaces.worker.tasks.regenerate_ad_copy_task",
)
def regenerate_ad_copy_task(
    brief_id: str,
    proposal_id: str,
    ad_group_index: int = 0,
) -> dict[str, object]:
    """Re-generate ad copy for one ad group of an existing proposal using the LLM."""
    import asyncio

    return asyncio.run(_run_regenerate_ad_copy(brief_id, proposal_id, ad_group_index))


async def _run_regenerate_ad_copy(
    brief_id: str,
    proposal_id: str,
    ad_group_index: int,
) -> dict[str, object]:
    from dataclasses import replace as dc_replace

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.launch.entities import (
        AdProposal,
        CampaignBriefId,
        CampaignProposalId,
    )
    from adcopilot.infrastructure.db.repositories.launch_brief_repository import (
        SqlCampaignBriefRepository,
    )
    from adcopilot.infrastructure.db.repositories.launch_proposal_repository import (
        SqlCampaignProposalRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with AsyncSession(engine) as session:
            brief_repo = SqlCampaignBriefRepository(session)
            brief = await brief_repo.get(CampaignBriefId(brief_id))
            if brief is None:
                logger.warning("regenerate_ad_copy: brief not found", brief_id=brief_id)
                return {"error": "brief_not_found"}

            proposal_repo = SqlCampaignProposalRepository(session)
            proposal = await proposal_repo.get(CampaignProposalId(proposal_id))
            if proposal is None or ad_group_index >= len(proposal.ad_groups):
                logger.warning(
                    "regenerate_ad_copy: proposal or ad group not found",
                    proposal_id=proposal_id,
                    ad_group_index=ad_group_index,
                )
                return {"error": "not_found"}

            if not settings.LLM_API_KEY:
                logger.warning("regenerate_ad_copy: no LLM API key configured")
                return {"error": "no_llm_key"}

            from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient

            llm = AnthropicClient(api_key=settings.LLM_API_KEY)
            ad_group = proposal.ad_groups[ad_group_index]

            prompt = (
                f"Wygeneruj 5 nagłówków (max 30 znaków każdy) i 2 opisy (max 90 znaków) "
                f"dla reklamy Google Ads dla firmy: {brief.business_description}. "
                f"Grupa reklam: '{ad_group.name}'. "
                f'Zwróć JSON: {{"headlines": [...], "descriptions": [...]}}. '
                f"Tylko JSON, bez dodatkowego tekstu."
            )

            try:
                raw = await llm.complete(prompt, max_tokens=400)
                import json as _json

                data = _json.loads(raw)
                new_headlines = [str(h)[:30] for h in data.get("headlines", [])[:15]]
                new_descriptions = [str(d)[:90] for d in data.get("descriptions", [])[:4]]
            except Exception as exc:
                logger.warning(
                    "regenerate_ad_copy: LLM failed",
                    error=str(exc),
                    proposal_id=proposal_id,
                )
                return {"error": "llm_failed"}
            finally:
                await llm.aclose()

            if len(new_headlines) < 3 or len(new_descriptions) < 2:
                return {"error": "llm_output_insufficient"}

            old_ad = ad_group.ads[0] if ad_group.ads else None
            new_ad = AdProposal(
                headlines=new_headlines,
                descriptions=new_descriptions,
                final_url=old_ad.final_url if old_ad else "https://example.com",
                path_segments=old_ad.path_segments if old_ad else ("", ""),
            )
            new_ads = [new_ad] + list(ad_group.ads[1:])
            updated_group = dc_replace(ad_group, ads=new_ads)
            groups = list(proposal.ad_groups)
            groups[ad_group_index] = updated_group
            updated_proposal = dc_replace(proposal, ad_groups=groups)

            async with session.begin():
                await proposal_repo.save(updated_proposal)

        logger.info(
            "regenerate_ad_copy: complete",
            proposal_id=proposal_id,
            ad_group_index=ad_group_index,
        )
        return {"proposal_id": proposal_id, "ad_group_index": ad_group_index}
    finally:
        await engine.dispose()


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
    error_reason: str | None = None
    campaign_rn: str | None = None
    _saved_refresh_token: str | None = None
    _saved_customer_id: str | None = None
    _saved_primary_action: str | None = None
    _saved_user_id: str | None = None
    _saved_campaign_name: str | None = None

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
            _saved_user_id = str(brief.user_id)

            proposal = await proposal_repo.get_by_brief(brief.id)
            if proposal is None:
                return {"error": "proposal_not_found"}
            _saved_campaign_name = proposal.campaign_name

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
                if (
                    campaign_rn
                    or ag_rns
                    or kw_rns
                    or ad_rns
                    or neg_rns
                    or ext_rns
                    or audience_rns
                    or brand_campaign_rn
                    or schedule_rns
                ):
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
        # Translate the Google Ads failure into a clear Polish reason the user
        # can act on, instead of a raw gRPC/enum payload.
        from adcopilot.infrastructure.google_ads.error_messages import (
            humanize_google_ads_error,
        )

        error_reason = humanize_google_ads_error(exc)
    finally:
        await engine.dispose()

    # Notify the user of the outcome via a web-app notification.
    if _saved_user_id:
        from adcopilot.infrastructure.notifications.web_notifier_adapter import SqlWebNotifier

        _name = _saved_campaign_name or "Twoja kampania"
        notif_engine = create_async_engine(settings.DATABASE_URL)
        try:
            async with AsyncSession(notif_engine) as notif_session, notif_session.begin():
                notifier = SqlWebNotifier(notif_session)
                if error_text:
                    reason = error_reason or (
                        "Spróbuj ponownie lub skontaktuj się z pomocą techniczną."
                    )
                    await notifier.send_execution_result(
                        user_id=_saved_user_id,
                        title="Nie udało się utworzyć kampanii",
                        body=f"Nie udało się utworzyć kampanii „{_name}”. {reason}",
                        metadata={
                            "brief_id": brief_id,
                            "error": error_text,
                            "reason": error_reason or "",
                        },
                    )
                else:
                    await notifier.send_execution_result(
                        user_id=_saved_user_id,
                        title="Kampania została utworzona",
                        body=(
                            f"Kampania „{_name}” została pomyślnie utworzona i jest wstrzymana. "
                            "Możesz ją teraz przejrzeć i uruchomić."
                        ),
                        metadata={
                            "brief_id": brief_id,
                            "campaign_resource_name": campaign_rn or "",
                        },
                    )
        except Exception:
            logger.exception("failed to send campaign outcome notification", brief_id=brief_id)
        finally:
            await notif_engine.dispose()

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

    return asyncio.run(_run_monitor_new_campaign(brief_id, account_id, hours_elapsed))


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

        client.copy_from(op.update_mask, field_mask_pb2.FieldMask(paths=["status"]))
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
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
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

        from adcopilot.domain.exceptions import GoogleAdsAuthError

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
            except GoogleAdsAuthError:
                # Mark the account for re-authentication and move on.
                logger.warning(
                    "anomaly_detection.auth_error — marking needs_reauth",
                    account_id=str(acct.id),
                )
                async with AsyncSession(engine) as session, session.begin():
                    _acct_repo = SqlGoogleAdsAccountRepository(session)
                    import dataclasses

                    updated = dataclasses.replace(acct, needs_reauth=True)
                    await _acct_repo.save(updated)
                accounts_errored += 1
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
                    logger.exception("bidding_upgrade_check.failed", account_id=str(account.id))
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
                    logger.exception("rlsa_eligibility_check.failed", account_id=str(account.id))
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


@celery_app.task(
    name="adcopilot.interfaces.worker.tasks.check_remarketing_campaign_eligibility_task"
)  # type: ignore[untyped-decorator]
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

                async def _fetch_snapshot(
                    account_id: str, entity_type: str, entity_id: int
                ) -> dict | None:
                    from datetime import date

                    today = date.today()
                    from adcopilot.domain.entities import AccountId

                    campaigns = await snapshot_repo.get_campaigns_by_date(
                        AccountId(account_id), today
                    )
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
        from sqlalchemy.ext.asyncio import AsyncSession

        from adcopilot.application.use_cases.classify_account_vertical import (
            ClassifyAccountVerticalUseCase,
        )
        from adcopilot.config import Settings
        from adcopilot.infrastructure.db.engine import build_async_engine
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )

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
        from sqlalchemy.ext.asyncio import AsyncSession

        from adcopilot.application.use_cases.aggregate_benchmarks import (
            AggregateBenchmarksUseCase,
        )
        from adcopilot.config import Settings
        from adcopilot.infrastructure.db.engine import build_async_engine
        from adcopilot.infrastructure.db.repositories.account_summary_provider import (
            SqlAccountSummaryProvider,
        )
        from adcopilot.infrastructure.db.repositories.benchmark_repository import (
            SqlBenchmarkRepository,
        )

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


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.monthly_landing_page_audit_task",
    max_retries=2,
    default_retry_delay=300,
)
def monthly_landing_page_audit_task() -> dict[str, object]:
    """Score all active landing pages monthly; alert users via WebNotifier if score < 50."""
    import asyncio as _asyncio

    async def _run() -> dict[str, object]:
        import asyncio
        import json

        import structlog
        from sqlalchemy.ext.asyncio import AsyncSession

        from adcopilot.application.use_cases.score_landing_page import LandingPageScoreUseCase
        from adcopilot.config import Settings
        from adcopilot.domain.exceptions import PageAnalyzerError
        from adcopilot.infrastructure.db.engine import build_async_engine
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
            SqlPromptVersionRepository,
        )
        from adcopilot.infrastructure.db.repositories.snapshot_repository import (
            SqlSnapshotRepository,
        )
        from adcopilot.infrastructure.landing_page.pagespeed_adapter import PageSpeedAdapter
        from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
        from adcopilot.infrastructure.notifications.web_notifier_adapter import SqlWebNotifier

        _log = structlog.get_logger(__name__)
        settings = Settings()
        engine = build_async_engine(settings)
        scored = 0
        alerted = 0
        errors = 0
        llm: AnthropicClient | None = None

        try:
            async with AsyncSession(engine) as session:
                account_repo = SqlGoogleAdsAccountRepository(session)
                snapshot_repo = SqlSnapshotRepository(session)
                prompt_repo = SqlPromptVersionRepository(session)
                notifier = SqlWebNotifier(session)

                accounts = await account_repo.list_active()
                llm = AnthropicClient(api_key=settings.LLM_API_KEY)
                psi_adapter = PageSpeedAdapter(api_key=settings.PAGESPEED_API_KEY)
                use_case = LandingPageScoreUseCase(
                    page_analyzer=psi_adapter, llm=llm, prompt_repo=prompt_repo
                )

                for account in accounts:
                    latest_date = await snapshot_repo.get_latest_snapshot_date(account.id)
                    if latest_date is None:
                        continue
                    ads = await snapshot_repo.get_ads_by_date(account.id, latest_date)
                    urls: set[str] = set()
                    for ad in ads:
                        try:
                            parsed = json.loads(ad.final_urls_json or "[]")
                            urls.update(u for u in parsed if u and u.startswith("http"))
                        except (json.JSONDecodeError, AttributeError):
                            pass

                    for url in sorted(urls):
                        try:
                            score = await use_case.execute(url)
                            scored += 1
                            if score.performance_score < 50:
                                await notifier.send_alert(
                                    user_id=str(account.user_id),
                                    title="Niska ocena strony docelowej",
                                    body=(
                                        f"Strona {url} uzyskała wynik wydajności "
                                        f"{score.performance_score}/100. "
                                        f"Rekomendacje: {'; '.join(score.recommendations_pl[:2])}."
                                    ),
                                )
                                alerted += 1
                        except PageAnalyzerError as exc:
                            _log.warning("monthly_audit.pagespeed_error", url=url, error=str(exc))
                            errors += 1
                        except Exception as exc:
                            _log.error("monthly_audit.unexpected_error", url=url, error=str(exc))
                            errors += 1

                        # 1-second delay per PSI quota mitigation (CCR-1)
                        await asyncio.sleep(1)

                await session.commit()
        finally:
            if llm is not None:
                await llm.aclose()
            await engine.dispose()

        _log.info("monthly_landing_page_audit.done", scored=scored, alerted=alerted, errors=errors)
        return {"scored": scored, "alerted": alerted, "errors": errors}

    return _asyncio.run(_run())


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.generate_weekly_insight_task",
    max_retries=2,
    default_retry_delay=120,
)
def generate_weekly_insight_task() -> dict[str, object]:
    """Generate and deliver weekly strategic insights to all active users (Monday 8:30 AM UTC)."""
    import asyncio as _asyncio

    async def _run() -> dict[str, object]:
        import structlog
        from sqlalchemy.ext.asyncio import AsyncSession

        from adcopilot.application.services.account_context_builder import AccountContextBuilder
        from adcopilot.application.use_cases.generate_weekly_insight import (
            GenerateWeeklyInsightUseCase,
        )
        from adcopilot.config import Settings
        from adcopilot.infrastructure.db.engine import build_async_engine
        from adcopilot.infrastructure.db.repositories.audit_log_repository import (
            SqlAuditLogRepository,
        )
        from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
            SqlGoogleAdsAccountRepository,
        )
        from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
            SqlPromptVersionRepository,
        )
        from adcopilot.infrastructure.db.repositories.recommendation_repository import (
            SqlRecommendationRepository,
        )
        from adcopilot.infrastructure.db.repositories.snapshot_repository import (
            SqlSnapshotRepository,
        )
        from adcopilot.infrastructure.db.repositories.weekly_insight_repository import (
            SqlWeeklyInsightRepository,
        )
        from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient
        from adcopilot.infrastructure.notifications.web_notifier_adapter import SqlWebNotifier

        _log = structlog.get_logger(__name__)
        settings = Settings()
        engine = build_async_engine(settings)
        delivered = 0
        errors = 0
        llm: AnthropicClient | None = None

        try:
            async with AsyncSession(engine) as session:
                account_repo = SqlGoogleAdsAccountRepository(session)
                snapshot_repo = SqlSnapshotRepository(session)
                rec_repo = SqlRecommendationRepository(session)
                audit_repo = SqlAuditLogRepository(session)
                prompt_repo = SqlPromptVersionRepository(session)
                notifier = SqlWebNotifier(session)
                insight_repo = SqlWeeklyInsightRepository(session)

                accounts = await account_repo.list_active()
                llm = AnthropicClient(api_key=settings.LLM_API_KEY)
                insight_uc = GenerateWeeklyInsightUseCase(llm=llm, prompt_repo=prompt_repo)

                for account in accounts:
                    try:
                        builder = AccountContextBuilder(
                            snapshot_repo=snapshot_repo,
                            rec_repo=rec_repo,
                            audit_log_repo=audit_repo,
                        )
                        ctx = await builder.build(account.id)
                        if ctx.get("summary") is None:
                            continue  # no data — skip

                        insight_text = await insight_uc.execute(ctx)

                        import datetime as _dt

                        today = _dt.date.today()
                        week_start = today - _dt.timedelta(days=today.weekday())

                        await insight_repo.save(
                            user_id=str(account.user_id),
                            account_id=str(account.id),
                            week_start=week_start,
                            insight_text=insight_text,
                            context_snapshot={
                                "snapshot_date": ctx.get("snapshot_date"),
                                "summary": ctx.get("summary"),
                            },
                        )
                        await notifier.send_insight(
                            user_id=str(account.user_id),
                            title="Tygodniowy raport strategiczny",
                            body=insight_text,
                            metadata={"account_id": str(account.id), "context_snapshot": ctx},
                        )
                        delivered += 1
                    except Exception as exc:
                        _log.error(
                            "weekly_insight.error", account_id=str(account.id), error=str(exc)
                        )
                        errors += 1

                await session.commit()
        finally:
            if llm is not None:
                await llm.aclose()
            await engine.dispose()

        _log.info("generate_weekly_insight.done", delivered=delivered, errors=errors)
        return {"delivered": delivered, "errors": errors}

    return _asyncio.run(_run())


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.send_conversion_tracking_reminders_task",
)
def send_conversion_tracking_reminders_task() -> dict[str, object]:
    """Send weekly Telegram reminders to accounts with broken/missing conversion tracking."""
    import asyncio as _asyncio

    from adcopilot.config import get_settings

    _settings = get_settings()
    return _asyncio.run(_run_conversion_reminders(_settings))


async def _run_conversion_reminders(settings: object) -> dict[str, object]:
    import httpx
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import Settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.models import UserModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository

    assert isinstance(settings, Settings)

    if not settings.TELEGRAM_BOT_TOKEN:
        logger.debug("conversion_reminders.skipped — TELEGRAM_BOT_TOKEN not set")
        return {"sent": 0, "skipped_no_token": True}

    engine = create_async_engine(settings.DATABASE_URL)
    sent = 0
    skipped = 0
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            snapshot_repo = SqlSnapshotRepository(session)

            result = await session.execute(
                select(UserModel).where(
                    UserModel.notifications_paused.is_(False),
                    UserModel.telegram_chat_id.isnot(None),
                )
            )
            users = result.scalars().all()

            for user in users:
                try:
                    accounts = await account_repo.list_for_user(user.id)  # type: ignore[arg-type]
                    for account in accounts:
                        latest_date = await snapshot_repo.get_latest_snapshot_date(
                            AccountId(str(account.id))
                        )
                        if latest_date is None:
                            continue
                        conversion_actions = await snapshot_repo.get_conversion_actions(
                            AccountId(str(account.id)), latest_date
                        )
                        has_working_tracking = any(
                            a.status == "ENABLED" and a.all_conversions > 0
                            for a in conversion_actions
                        )
                        if not has_working_tracking and user.telegram_chat_id:
                            message = (
                                "⚠️ Twoje śledzenie konwersji Google Ads nie jest skonfigurowane lub nie działa. "
                                "Optymalizacja kampanii jest ograniczona — brakuje danych o konwersjach.\n\n"
                                "Przejdź do panelu Adswise → Śledzenie Konwersji, aby skonfigurować."
                            )
                            async with httpx.AsyncClient(timeout=10.0) as client:
                                await client.post(
                                    f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage",
                                    json={"chat_id": user.telegram_chat_id, "text": message},
                                )
                            sent += 1
                        else:
                            skipped += 1
                except Exception as exc:
                    logger.warning(
                        "conversion_reminders.user_error",
                        user_id=str(user.id),
                        error=str(exc),
                    )
    finally:
        await engine.dispose()

    logger.info("conversion_reminders.done", sent=sent, skipped=skipped)
    return {"sent": sent, "skipped": skipped}


@celery_app.task(name="adcopilot.interfaces.worker.tasks.snapshot_ga4_data_task")  # type: ignore[untyped-decorator]
def snapshot_ga4_data_task(account_id: str, snapshot_date_iso: str) -> dict:
    """Pull GA4 page metrics for a given account and store in ga4_page_snapshots."""
    import asyncio
    from datetime import date as date_type

    snap_date = date_type.fromisoformat(snapshot_date_iso)
    result = asyncio.run(_run_ga4_snapshot(account_id, snap_date))
    return result


async def _run_ga4_snapshot(account_id: str, snap_date) -> dict:
    import base64
    import hashlib
    import uuid as _uuid

    from cryptography.fernet import Fernet
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.models import GA4CredentialsModel, GA4PageSnapshotModel
    from adcopilot.infrastructure.ga4.queries_adapter import fetch_page_metrics

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(GA4CredentialsModel).where(
                    GA4CredentialsModel.account_id == _uuid.UUID(account_id)
                )
            )
            creds = result.scalar_one_or_none()
            if creds is None or not creds.property_id:
                return {"skipped": True, "reason": "no_ga4_credentials"}

            key = base64.urlsafe_b64encode(
                hashlib.sha256(settings.TOKEN_ENCRYPTION_KEY.encode()).digest()
            )
            fernet = Fernet(key)
            refresh_token = fernet.decrypt(creds.refresh_token_enc.encode()).decode()

        metrics = await fetch_page_metrics(
            property_id=creds.property_id,
            refresh_token=refresh_token,
            client_id=settings.GOOGLE_ADS_CLIENT_ID or "",
            client_secret=settings.GOOGLE_ADS_CLIENT_SECRET or "",
            snapshot_date=snap_date,
        )
        if not metrics:
            return {"rows": 0}

        rows = [
            {
                "id": _uuid.uuid4(),
                "account_id": _uuid.UUID(account_id),
                "snapshot_date": snap_date,
                "page_path": m.page_path,
                "sessions": m.sessions,
                "bounce_rate": m.bounce_rate,
                "avg_session_duration_sec": m.avg_session_duration_sec,
                "pages_per_session": m.pages_per_session,
            }
            for m in metrics
        ]
        async with AsyncSession(engine) as session, session.begin():
            stmt = pg_insert(GA4PageSnapshotModel).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_ga4_page_snapshots_account_date_path",
                set_={
                    "sessions": stmt.excluded.sessions,
                    "bounce_rate": stmt.excluded.bounce_rate,
                    "avg_session_duration_sec": stmt.excluded.avg_session_duration_sec,
                    "pages_per_session": stmt.excluded.pages_per_session,
                },
            )
            await session.execute(stmt)
        logger.info("ga4_snapshot_done", account_id=account_id, rows=len(rows))
        return {"rows": len(rows)}
    except Exception as exc:
        logger.warning("ga4_snapshot_failed", account_id=account_id, error=str(exc))
        return {"error": str(exc)}
    finally:
        await engine.dispose()


@celery_app.task(name="adcopilot.interfaces.worker.tasks.snapshot_auction_insights_task")  # type: ignore[untyped-decorator]
def snapshot_auction_insights_task(account_id: str, snapshot_date_iso: str) -> dict:
    """Fetch and store Auction Insights for one account (weekly)."""
    import asyncio
    from datetime import date as date_type

    snap_date = date_type.fromisoformat(snapshot_date_iso)
    return asyncio.run(_run_auction_insights_snapshot(account_id, snap_date))


async def _run_auction_insights_snapshot(account_id: str, snap_date) -> dict:
    import uuid as _uuid

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.models import AuctionInsightsSnapshotModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
            account = await account_repo.get(account_id)
            if account is None:
                return {"skipped": True, "reason": "no_account"}
            credentials = await credentials_repo.get(AccountId(account_id))
            if credentials is None:
                return {"skipped": True, "reason": "no_credentials"}

            refresh_token = credentials.refresh_token
            customer_id = account.customer_id

        adapter = GoogleAdsQueriesAdapter(settings)
        rows_data = await adapter.fetch_auction_insights(refresh_token, customer_id, snap_date)

        if not rows_data:
            return {"rows": 0}

        rows = [
            {
                "id": _uuid.uuid4(),
                "account_id": _uuid.UUID(account_id),
                "campaign_id": r["campaign_id"],
                "competitor_domain": r["competitor_domain"],
                "impression_share": r["impression_share"],
                "overlap_rate": r["overlap_rate"],
                "position_above_rate": r["position_above_rate"],
                "snapshot_date": snap_date,
            }
            for r in rows_data
            if r.get("competitor_domain")
        ]
        if not rows:
            return {"rows": 0}

        async with AsyncSession(engine) as session, session.begin():
            stmt = pg_insert(AuctionInsightsSnapshotModel).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_auction_insights_per_day",
                set_={
                    "impression_share": stmt.excluded.impression_share,
                    "overlap_rate": stmt.excluded.overlap_rate,
                    "position_above_rate": stmt.excluded.position_above_rate,
                },
            )
            await session.execute(stmt)

        logger.info("auction_insights_snapshot_done", account_id=account_id, rows=len(rows))
        return {"rows": len(rows)}
    except Exception as exc:
        logger.warning("auction_insights_snapshot_failed", account_id=account_id, error=str(exc))
        return {"error": str(exc)}
    finally:
        await engine.dispose()


@celery_app.task(name="adcopilot.interfaces.worker.tasks.weekly_qs_improvement_check_task")
def weekly_qs_improvement_check_task() -> dict:
    """Weekly QS improvement check: auto-create plans and evaluate measuring ones."""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(_weekly_qs_improvement_check())


async def _weekly_qs_improvement_check() -> dict:
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.qs_improvement_plan_repository import (
        QSImprovementPlanRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    created = 0
    evaluated = 0
    try:
        async with AsyncSession(engine) as session:
            # 1. Auto-create plans for accounts with low-QS keywords and no active plan
            account_repo = SqlGoogleAdsAccountRepository(session)
            all_accounts = await account_repo.list_active()
            qs_repo = QSImprovementPlanRepository(session)
            for account in all_accounts:
                try:
                    active = await qs_repo.list_active_for_account(str(account.id))
                    if active:
                        continue
                    from adcopilot.application.use_cases.create_qs_improvement_plan import (
                        create_qs_improvement_plan,
                    )

                    plan = await create_qs_improvement_plan(
                        account_id=str(account.id), session=session
                    )
                    await qs_repo.save(plan)
                    created += 1
                except ValueError:
                    pass
                except Exception as exc:
                    logger.warning(
                        "qs_auto_create_failed", account_id=str(account.id), error=str(exc)
                    )

            # 2. Evaluate plans past their measurement window
            now = datetime.now(UTC)
            measuring = await qs_repo.list_measuring_past_window(now)
            for plan in measuring:
                try:
                    from adcopilot.application.use_cases.evaluate_qs_improvement_plan import (
                        evaluate_qs_improvement_plan,
                    )

                    await evaluate_qs_improvement_plan(plan_id=plan.id, session=session)
                    evaluated += 1
                except Exception as exc:
                    logger.warning("qs_eval_failed", plan_id=plan.id, error=str(exc))

            await session.commit()
    finally:
        await engine.dispose()

    logger.info("weekly_qs_improvement_check_done", created=created, evaluated=evaluated)
    return {"created": created, "evaluated": evaluated}


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.monthly_performance_reports_task"
)
def monthly_performance_reports_task() -> None:
    """Generate monthly performance reports for all active accounts."""
    import asyncio

    asyncio.run(_monthly_performance_reports())


async def _monthly_performance_reports() -> None:
    """For all active accounts, generate last-month performance report."""
    from datetime import date, timedelta

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.generate_performance_report import (
        generate_performance_report,
    )
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import (
        SqlPromptVersionRepository,
    )
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient as AnthropicLLMClient
    from adcopilot.infrastructure.reporting.pdf_renderer import render_performance_report_pdf

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)

    today = date.today()
    period_end = date(today.year, today.month, 1) - timedelta(days=1)
    period_start = date(period_end.year, period_end.month, 1)

    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_active()

        for account in accounts:
            account_id = str(account.id)
            user_id = str(account.user_id)
            llm: AnthropicLLMClient | None = None
            try:
                async with AsyncSession(engine) as session:
                    prompt_repo = SqlPromptVersionRepository(session)
                    llm = AnthropicLLMClient(api_key=settings.LLM_API_KEY or "")
                    report_data = await generate_performance_report(
                        user_id=user_id,
                        account_id=account_id,
                        period_start=period_start,
                        period_end=period_end,
                        session=session,
                        llm=llm,
                        prompt_repo=prompt_repo,
                    )
                    pdf_bytes = render_performance_report_pdf(report_data)

                    import json as _json
                    import uuid as _uuid

                    from sqlalchemy import text as _text

                    await session.execute(
                        _text(
                            """
                            INSERT INTO performance_reports
                                (id, user_id, account_id, period_start, period_end, report_data, summary_pl, pdf_bytes)
                            VALUES
                                (:id, :user_id, :account_id, :period_start, :period_end, :report_data::jsonb, :summary_pl, :pdf_bytes)
                            """
                        ),
                        {
                            "id": str(_uuid.uuid4()),
                            "user_id": user_id,
                            "account_id": account_id,
                            "period_start": period_start,
                            "period_end": period_end,
                            "report_data": _json.dumps(report_data),
                            "summary_pl": report_data.get("summary_pl"),
                            "pdf_bytes": pdf_bytes,
                        },
                    )
                    await session.commit()
                    logger.info(
                        "monthly_performance_report.generated",
                        account_id=account_id,
                        period_start=period_start.isoformat(),
                        period_end=period_end.isoformat(),
                    )
            except Exception as exc:
                logger.warning(
                    "monthly_performance_report.failed",
                    account_id=account_id,
                    error=str(exc),
                )
            finally:
                if llm is not None:
                    await llm.aclose()
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Post-launch check-in Celery tasks (Phase 6)
# ---------------------------------------------------------------------------


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.post_launch_checkins_task",
)
def post_launch_checkins_task() -> dict[str, object]:
    """Send check-in notifications for campaigns launched 3, 7, 14, or 30 days ago."""
    import asyncio

    return asyncio.run(_run_post_launch_checkins())


async def _run_post_launch_checkins() -> dict[str, object]:
    from datetime import UTC, date, datetime, timedelta

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.services.checkin_aggregator import (
        CheckInAggregator,
    )
    from adcopilot.application.services.post_launch_notifier import PostLaunchNotifier
    from adcopilot.config import get_settings
    from adcopilot.domain.launch.entities import LaunchStatus
    from adcopilot.infrastructure.db.models import LaunchBriefModel
    from adcopilot.infrastructure.db.repositories.notification_repository import (
        SqlNotificationRepository,
    )
    from adcopilot.infrastructure.db.repositories.snapshot_repository import (
        SqlSnapshotRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    today = date.today()
    checkin_days = [3, 7, 14, 30]
    sent = 0

    # Map days to template keys
    template_key_map = {
        3: "day_3_no_data",  # default; overridden below if data available
        7: "day_7_performance",
        14: "day_14_insight",
        30: "day_30_summary",
    }

    try:
        for days in checkin_days:
            target_date = today - timedelta(days=days)
            async with AsyncSession(engine) as session:
                result = await session.execute(
                    select(LaunchBriefModel).where(
                        LaunchBriefModel.status == LaunchStatus.ENABLED,
                        LaunchBriefModel.created_at
                        >= datetime(
                            target_date.year,
                            target_date.month,
                            target_date.day,
                            0,
                            0,
                            0,
                            tzinfo=UTC,
                        ),
                        LaunchBriefModel.created_at
                        < datetime(
                            target_date.year,
                            target_date.month,
                            target_date.day,
                            23,
                            59,
                            59,
                            tzinfo=UTC,
                        ),
                    )
                )
                briefs = result.scalars().all()

                class _SnapshotRepoAdapter:
                    """Wraps SqlSnapshotRepository to provide list_by_account()."""

                    def __init__(self, inner):
                        self._inner = inner

                    async def list_by_account(self, account_id, limit=7):
                        from datetime import date, timedelta

                        from adcopilot.domain.entities import AccountId

                        snaps = []
                        for delta in range(limit):
                            d = date.today() - timedelta(days=delta)
                            try:
                                day_snaps = await self._inner.get_campaigns_by_date(
                                    AccountId(account_id), d
                                )
                                snaps.extend(day_snaps)
                            except Exception:
                                pass
                        return snaps

                snap_repo = _SnapshotRepoAdapter(SqlSnapshotRepository(session))
                aggregator = CheckInAggregator(snap_repo)

                for brief in briefs:
                    try:
                        campaign_name = brief.business_description[:60]
                        account_id = str(brief.account_id)

                        metrics = await aggregator.get_metrics(
                            account_id, brief.campaign_resource_name
                        )

                        if days == 3:
                            tmpl_key = "day_3_no_data" if metrics.is_empty else "day_3_with_data"
                        else:
                            tmpl_key = template_key_map[days]

                        notifier = PostLaunchNotifier(SqlNotificationRepository(session))
                        await notifier.notify_checkin(
                            user_id=str(brief.user_id),
                            campaign_name=campaign_name,
                            account_id=account_id,
                            days_since_launch=days,
                            clicks=metrics.clicks,
                            impressions=metrics.impressions,
                            cost_pln=metrics.cost_pln,
                            conversions=metrics.conversions,
                        )
                        await session.commit()
                        sent += 1
                        logger.debug(
                            "post_launch_checkin.sent",
                            brief_id=str(brief.id),
                            days=days,
                            template=tmpl_key,
                            ctr=metrics.ctr,
                        )
                    except Exception as exc:
                        logger.warning(
                            "post_launch_checkin.failed",
                            brief_id=str(brief.id),
                            days=days,
                            error=str(exc),
                        )
    finally:
        await engine.dispose()

    logger.info("post_launch_checkins_task.complete", sent=sent, today=today.isoformat())
    return {"sent": sent}


@celery_app.task(  # type: ignore[untyped-decorator]
    name="adcopilot.interfaces.worker.tasks.weekly_conversion_tracking_reminders_task",
)
def weekly_conversion_tracking_reminders_task() -> dict[str, object]:
    """Remind users with active campaigns that have no conversion tracking configured."""
    import asyncio

    return asyncio.run(_run_weekly_conversion_tracking_reminders())


async def _run_weekly_conversion_tracking_reminders() -> dict[str, object]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.services.post_launch_notifier import PostLaunchNotifier
    from adcopilot.config import get_settings
    from adcopilot.domain.launch.entities import LaunchStatus
    from adcopilot.infrastructure.adapters.google_ads_conversion_adapter import (
        GoogleAdsConversionAdapter,
    )
    from adcopilot.infrastructure.db.models import LaunchBriefModel
    from adcopilot.infrastructure.db.repositories.notification_repository import (
        SqlNotificationRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    sent = 0
    checked = 0

    try:
        async with AsyncSession(engine) as session:
            result = await session.execute(
                select(LaunchBriefModel).where(LaunchBriefModel.status == LaunchStatus.ENABLED)
            )
            enabled_briefs = result.scalars().all()
            # Deduplicate by account
            seen_accounts: set[str] = set()
            for brief in enabled_briefs:
                account_id = str(brief.account_id)
                if account_id in seen_accounts:
                    continue
                seen_accounts.add(account_id)
                checked += 1

                try:
                    from adcopilot.domain.entities import AccountId

                    creds_repo = SqlOAuthCredentialsRepository(
                        session, settings.TOKEN_ENCRYPTION_KEY
                    )
                    creds = await creds_repo.get(AccountId(account_id))
                    if creds is None:
                        continue

                    google_ads_client = GoogleAdsQueriesAdapter(settings)
                    adapter = GoogleAdsConversionAdapter(google_ads_client)
                    status = await adapter.check(creds.refresh_token, account_id)

                    if not status.has_conversion_tracking:
                        notifier = PostLaunchNotifier(SqlNotificationRepository(session))
                        await notifier.notify_conversion_tracking_reminder(
                            user_id=str(brief.user_id),
                            account_id=account_id,
                            campaign_name=brief.business_description[:60],
                        )
                        await session.commit()
                        sent += 1
                except Exception as exc:
                    logger.warning(
                        "weekly_conversion_tracking_reminder.failed",
                        account_id=account_id,
                        error=str(exc),
                    )
    finally:
        await engine.dispose()

    logger.info(
        "weekly_conversion_tracking_reminders_task.complete",
        checked=checked,
        sent=sent,
    )
    return {"checked": checked, "sent": sent}
