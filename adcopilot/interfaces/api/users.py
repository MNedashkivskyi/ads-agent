"""User data endpoints."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Annotated, Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import AccountId, PlanTier, UserId
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])

# ---------------------------------------------------------------------------
# Plan → max-accounts mapping (single source of truth)
# ---------------------------------------------------------------------------

PLAN_MAX_ACCOUNTS: dict[str, int] = {
    PlanTier.STARTER.value: 1,
    PlanTier.GROWTH.value: 3,
    PlanTier.PRO.value: 10,
}


def _max_accounts_for_plan(plan: str) -> int:
    return PLAN_MAX_ACCOUNTS.get(plan, 1)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AccountResponse(BaseModel):
    id: str
    customer_id: str
    descriptive_name: str
    currency: str
    timezone: str
    is_manager: bool
    write_enabled: bool
    needs_reauth: bool
    connected_at: str


class StatsResponse(BaseModel):
    total_savings_micros: int
    executed_count: int
    pending_count: int
    declined_count: int


class RecommendationResponse(BaseModel):
    id: str
    account_id: str
    kind: str
    severity: str
    confidence: str = "MEDIUM"
    status: str
    estimated_monthly_savings_micros: int
    explanation: str | None
    created_at: str
    evidence: dict[str, object] | None = None
    is_executable: bool = True
    is_undoable: bool = False


class AuditLogResponse(BaseModel):
    id: str
    recommendation_id: str
    account_id: str
    kind: str
    action: str
    payload: dict[str, Any]
    created_at: str


class SettingsUpdateRequest(BaseModel):
    notification_hour: int | None = None
    language: str | None = None


class UserMeResponse(BaseModel):
    user_id: str
    email: str
    telegram_chat_id: int | None
    role: str  # "admin" | "client"
    plan: str  # "starter" | "growth" | "pro"
    max_accounts: int
    subscription_status: str  # "trialing" | "active" | "canceled" | ...
    trial_started_at: str | None


class AccountSyncStatus(BaseModel):
    account_id: str
    customer_id: str
    descriptive_name: str
    connected_at: str
    has_snapshots: bool
    sync_in_progress: bool  # True while the initial snapshot task is running
    last_snapshot_date: str | None
    started_at: str | None  # ISO timestamp when the sync task was queued
    error: str | None  # Error message if the sync failed


class SyncStatusResponse(BaseModel):
    syncing: bool  # True if any account still has sync_in_progress
    has_errors: bool  # True if any account had a sync error
    accounts: list[AccountSyncStatus]
    estimated_seconds_remaining: int | None  # rough ETA for first sync


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{user_id}/me", response_model=UserMeResponse)
async def get_user_me(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserMeResponse:
    """Return basic user info including Telegram connection status.

    On first call for a brand-new user (no existing record), a minimal row
    is auto-created with plan=starter, subscription_status=trialing, and
    trial_started_at set to now.  This powers the "Start free trial" CTA —
    the trial begins the moment the frontend calls /me after signup.
    """
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.ensure_exists(UserId(user_id))

            # Auto-start trial: if subscription_status is trialing and
            # trial_started_at hasn't been set yet, stamp it now.
            if user.subscription_status == "trialing" and user.trial_started_at is None:
                user = dataclasses.replace(user, trial_started_at=datetime.now(UTC))
                await repo.save(user)

            await session.commit()

            admin_ids = {uid.strip() for uid in settings.ADMIN_USER_IDS.split(",") if uid.strip()}
            role = "admin" if user_id in admin_ids else "client"
            return UserMeResponse(
                user_id=str(user.id),
                email=user.email,
                telegram_chat_id=user.telegram_chat_id,
                role=role,
                plan=user.plan.value,
                max_accounts=_max_accounts_for_plan(user.plan.value),
                subscription_status=user.subscription_status,
                trial_started_at=user.trial_started_at.isoformat()
                if user.trial_started_at
                else None,
            )
    finally:
        await engine.dispose()


@router.post("/{user_id}/start-trial")
async def start_trial(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Explicitly start the free trial (idempotent).

    If the user already has trial_started_at set, this is a no-op.
    """
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")

            if user.trial_started_at is not None:
                return {"status": "already_started"}

            user = dataclasses.replace(
                user,
                trial_started_at=datetime.now(UTC),
                subscription_status="trialing",
            )
            await repo.save(user)
            await session.commit()
    finally:
        await engine.dispose()

    logger.info("trial.started", user_id=user_id)
    return {"status": "trial_started"}


@router.get("/{user_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AccountResponse]:
    """List Google Ads accounts connected by the user."""
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlGoogleAdsAccountRepository(session)
            accounts = await repo.list_for_user(UserId(user_id))
    finally:
        await engine.dispose()

    return [
        AccountResponse(
            id=a.id,
            customer_id=a.customer_id,
            descriptive_name=a.descriptive_name,
            currency=a.currency,
            timezone=a.timezone,
            is_manager=a.is_manager,
            write_enabled=a.write_enabled,
            needs_reauth=a.needs_reauth,
            connected_at=a.connected_at.isoformat(),
        )
        for a in accounts
    ]


@router.get("/{user_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SyncStatusResponse:
    """Check whether initial data sync has completed for the user's accounts.

    Returns per-account snapshot status and an estimated time remaining
    so the frontend can render a progress indicator.
    """
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    import uuid as _uuid

    from redis import Redis
    from sqlalchemy import func, select

    from adcopilot.infrastructure.db.models import CampaignSnapshotModel, GoogleAdsAccountModel

    redis = Redis.from_url(settings.REDIS_URL)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            acct_result = await session.execute(
                select(GoogleAdsAccountModel).where(
                    GoogleAdsAccountModel.user_id == _uuid.UUID(user_id)
                )
            )
            accounts = acct_result.scalars().all()

            if not accounts:
                return SyncStatusResponse(
                    syncing=False, has_errors=False, accounts=[], estimated_seconds_remaining=None
                )

            statuses: list[AccountSyncStatus] = []
            any_syncing = False
            total_elapsed = 0.0

            for acct in accounts:
                acct_id_str = str(acct.id)

                # Check the Redis marker set by link_google_ads_accounts_task.
                # This is the authoritative signal for "sync in progress".
                redis_key = f"sync:initial:{acct_id_str}"
                started_raw = redis.get(redis_key)
                sync_in_progress = started_raw is not None
                started_at_iso: str | None = None

                if sync_in_progress:
                    any_syncing = True
                    started_at_iso = started_raw.decode() if started_raw else None
                    # Calculate elapsed time for ETA
                    if started_at_iso:
                        try:
                            started_dt = datetime.fromisoformat(started_at_iso)
                            elapsed = (datetime.now(UTC) - started_dt).total_seconds()
                            total_elapsed = max(total_elapsed, elapsed)
                        except (ValueError, TypeError):
                            pass

                # Check for sync error
                error_raw = redis.get(f"sync:error:{acct_id_str}")
                error_msg: str | None = error_raw.decode() if error_raw else None

                snap_result = await session.execute(
                    select(func.max(CampaignSnapshotModel.snapshot_date)).where(
                        CampaignSnapshotModel.account_id == acct.id
                    )
                )
                last_date = snap_result.scalar_one_or_none()
                has_snapshots = last_date is not None

                statuses.append(
                    AccountSyncStatus(
                        account_id=acct_id_str,
                        customer_id=acct.customer_id,
                        descriptive_name=acct.descriptive_name or "",
                        connected_at=acct.connected_at.isoformat()
                        if acct.connected_at
                        else "",
                        has_snapshots=has_snapshots,
                        sync_in_progress=sync_in_progress,
                        last_snapshot_date=str(last_date) if last_date else None,
                        started_at=started_at_iso,
                        error=error_msg,
                    )
                )

            # ETA: ~120s per account, minus time already elapsed
            pending_count = sum(1 for s in statuses if s.sync_in_progress)
            has_errors = any(s.error is not None for s in statuses)
            if any_syncing:
                raw_eta = max(0, pending_count * 120 - total_elapsed)
                estimated = int(raw_eta) if raw_eta > 0 else 10
            else:
                estimated = None

            return SyncStatusResponse(
                syncing=any_syncing,
                has_errors=has_errors,
                accounts=statuses,
                estimated_seconds_remaining=estimated,
            )
    finally:
        await engine.dispose()


@router.delete("/{user_id}/accounts/{account_id}", status_code=204)
async def delete_account(
    user_id: str,
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """Delete the link between user and Google Ads account.

    Also revokes the OAuth refresh token at Google so the user's grant is
    fully cleaned up.  Returns 204 on success.
    """
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import base64
    import hashlib
    import uuid as uuid_mod

    from cryptography.fernet import Fernet
    from sqlalchemy import select

    from adcopilot.infrastructure.db.models import GoogleAdsAccountModel, OAuthCredentialsModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    refresh_token: str | None = None
    try:
        async with AsyncSession(engine) as session:
            # Verify account belongs to the requesting user.
            result = await session.execute(
                select(GoogleAdsAccountModel).where(
                    GoogleAdsAccountModel.id == uuid_mod.UUID(account_id),
                    GoogleAdsAccountModel.user_id == uuid_mod.UUID(user_id),
                )
            )
            account_model = result.scalar_one_or_none()
            if account_model is None:
                raise HTTPException(status_code=404, detail="Account not found")

            # Retrieve and decrypt the refresh token for revocation.
            cred_result = await session.execute(
                select(OAuthCredentialsModel).where(
                    OAuthCredentialsModel.account_id == uuid_mod.UUID(account_id)
                )
            )
            cred_model = cred_result.scalar_one_or_none()
            if cred_model and cred_model.refresh_token_encrypted:
                try:
                    fernet_key = base64.urlsafe_b64encode(
                        hashlib.sha256(settings.TOKEN_ENCRYPTION_KEY.encode()).digest()
                    )
                    fernet = Fernet(fernet_key)
                    refresh_token = fernet.decrypt(
                        cred_model.refresh_token_encrypted.encode()
                    ).decode()
                except Exception:
                    logger.warning(
                        "failed to decrypt refresh token for revocation",
                        account_id=account_id,
                    )

            # Delete OAuth credentials first (FK-like dependency).
            if cred_model:
                await session.delete(cred_model)

            # Delete the account row.
            await session.delete(account_model)
            await session.commit()
    finally:
        await engine.dispose()

    # Best-effort revoke the refresh token at Google (fire-and-forget).
    if refresh_token:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(
                    "https://oauth2.googleapis.com/revoke",
                    params={"token": refresh_token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            logger.info("google token revoked", account_id=account_id)
        except Exception:
            # Revocation is best-effort — don't fail the DELETE if Google is
            # unreachable.  The token will expire on its own.
            logger.warning("google token revocation failed", account_id=account_id)

    logger.info("account.deleted", user_id=user_id, account_id=account_id)


@router.get("/{user_id}/stats", response_model=StatsResponse)
async def get_stats(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatsResponse:
    """Get cumulative savings and recommendation counts for the user."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from adcopilot.domain.recommendation import RecommendationStatus
    from adcopilot.infrastructure.db.models import RecommendationModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import func, select

            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                return StatsResponse(
                    total_savings_micros=0,
                    executed_count=0,
                    pending_count=0,
                    declined_count=0,
                )

            import uuid as uuid_mod

            account_uuids = [uuid_mod.UUID(a.id) for a in accounts]

            savings_result = await session.execute(
                select(func.sum(RecommendationModel.estimated_monthly_savings_micros)).where(
                    RecommendationModel.account_id.in_(account_uuids),
                    RecommendationModel.status == RecommendationStatus.EXECUTED.value,
                )
            )
            total_savings: int = savings_result.scalar_one() or 0

            counts_result = await session.execute(
                select(RecommendationModel.status, func.count())
                .where(RecommendationModel.account_id.in_(account_uuids))
                .group_by(RecommendationModel.status)
            )
            counts: dict[str, int] = {row[0]: row[1] for row in counts_result.all()}
    finally:
        await engine.dispose()

    return StatsResponse(
        total_savings_micros=total_savings,
        executed_count=counts.get(RecommendationStatus.EXECUTED.value, 0),
        pending_count=counts.get(RecommendationStatus.PENDING.value, 0),
        declined_count=counts.get(RecommendationStatus.DECLINED.value, 0),
    )


@router.get("/{user_id}/recommendations", response_model=list[RecommendationResponse])
async def list_recommendations(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[RecommendationResponse]:
    """List all recommendations across the user's accounts."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import uuid as uuid_mod

    from adcopilot.domain.recommendation import RecommendationStatus
    from adcopilot.infrastructure.db.models import RecommendationModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                return []

            account_uuids = [uuid_mod.UUID(a.id) for a in accounts]
            result = await session.execute(
                select(RecommendationModel)
                .where(
                    RecommendationModel.account_id.in_(account_uuids),
                    # Hide EXPIRED recs — they are no longer actual (issue
                    # resolved, or the campaign was removed) and must not appear.
                    RecommendationModel.status != RecommendationStatus.EXPIRED.value,
                )
                .order_by(RecommendationModel.created_at.desc())
            )
            recs = result.scalars().all()

            # Compute which EXECUTED recommendations are still within the undo
            # window so the UI can show/hide the Undo action precisely. One
            # batched query (latest EXECUTE audit per rec) avoids N+1 lookups.
            undoable_ids: set = set()
            executed_ids = [
                r.id for r in recs if r.status == RecommendationStatus.EXECUTED.value
            ]
            if executed_ids:
                from datetime import UTC, datetime, timedelta

                from sqlalchemy import func

                from adcopilot.application.use_cases.undo_recommendation import (
                    UNDO_WINDOW_DAYS,
                )
                from adcopilot.infrastructure.db.models import AuditLogModel

                cutoff = datetime.now(UTC) - timedelta(days=UNDO_WINDOW_DAYS)
                exec_rows = await session.execute(
                    select(
                        AuditLogModel.recommendation_id,
                        func.max(AuditLogModel.created_at),
                    )
                    .where(
                        AuditLogModel.recommendation_id.in_(executed_ids),
                        AuditLogModel.action == "EXECUTE",
                    )
                    .group_by(AuditLogModel.recommendation_id)
                )
                for rec_uuid, last_exec in exec_rows.all():
                    if last_exec is None:
                        continue
                    ts = last_exec if last_exec.tzinfo else last_exec.replace(tzinfo=UTC)
                    if ts >= cutoff:
                        undoable_ids.add(rec_uuid)
    finally:
        await engine.dispose()

    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS, RecommendationKind

    non_exec_values = {k.value for k in NON_EXECUTABLE_KINDS}
    return [
        RecommendationResponse(
            id=str(r.id),
            account_id=str(r.account_id),
            kind=r.kind,
            severity=r.severity,
            confidence=getattr(r, "confidence", None) or "MEDIUM",
            status=r.status,
            estimated_monthly_savings_micros=r.estimated_monthly_savings_micros,
            explanation=r.explanation,
            created_at=r.created_at.isoformat(),
            evidence=dict(r.evidence) if r.evidence else None,
            is_executable=r.kind not in non_exec_values,
            is_undoable=r.id in undoable_ids,
        )
        for r in recs
    ]


@router.post("/{user_id}/recommendations/refresh")
async def refresh_recommendations(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Re-run detection and generate explanations for all accounts of the user."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Cannot refresh another user's recommendations")

    from adcopilot.interfaces.worker.tasks import snapshot_account_task

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
                SqlGoogleAdsAccountRepository,
            )

            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                return {"queued": 0}

            from datetime import date as date_type

            today_iso = date_type.today().isoformat()
            for account in accounts:
                snapshot_account_task.delay(str(account.id), today_iso)

            return {"queued": len(accounts)}
    finally:
        await engine.dispose()


@router.get("/{user_id}/recommendations/last-refreshed")
async def recommendations_last_refreshed(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str | None]:
    """Return when recommendation data was last refreshed for the user.

    Derived from the most recent campaign snapshot write (snapshots are
    upserted on every refresh), which reflects the last successful data pull
    and detection run.
    """
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import uuid as uuid_mod

    from sqlalchemy import func, select

    from adcopilot.infrastructure.db.models import CampaignSnapshotModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                return {"last_refreshed_at": None}

            account_uuids = [uuid_mod.UUID(a.id) for a in accounts]
            result = await session.execute(
                select(func.max(CampaignSnapshotModel.updated_at)).where(
                    CampaignSnapshotModel.account_id.in_(account_uuids)
                )
            )
            last_refreshed = result.scalar_one_or_none()
    finally:
        await engine.dispose()

    return {"last_refreshed_at": last_refreshed.isoformat() if last_refreshed else None}


@router.get("/{user_id}/audit-log", response_model=list[AuditLogResponse])
async def list_audit_log(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AuditLogResponse]:
    """List audit log entries for the user's accounts (last 90 days)."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import uuid as uuid_mod
    from datetime import timedelta

    from adcopilot.infrastructure.db.models import AuditLogModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    since = datetime.now(UTC) - timedelta(days=90)
    try:
        async with AsyncSession(engine) as session:
            from sqlalchemy import select

            account_repo = SqlGoogleAdsAccountRepository(session)
            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                return []

            account_uuids = [uuid_mod.UUID(a.id) for a in accounts]
            result = await session.execute(
                select(AuditLogModel)
                .where(
                    AuditLogModel.account_id.in_(account_uuids),
                    AuditLogModel.created_at >= since,
                )
                .order_by(AuditLogModel.created_at.desc())
            )
            entries = result.scalars().all()
    finally:
        await engine.dispose()

    return [
        AuditLogResponse(
            id=str(e.id),
            recommendation_id=str(e.recommendation_id),
            account_id=str(e.account_id),
            kind=e.kind,
            action=e.action,
            payload=dict(e.payload),
            created_at=e.created_at.isoformat(),
        )
        for e in entries
    ]


_INACTIVE_SUBSCRIPTION_STATUSES = {"past_due", "canceled", "unpaid", "incomplete_expired"}


async def _assert_active_subscription(session: AsyncSession, user_id: str) -> None:
    """Reject (402) when the user's subscription is inactive or the trial expired.

    LAUNCH-015: subscription_status was recorded but never enforced — users
    (incl. canceled/past_due/expired-trial) could approve & execute changes for
    free. This is the paywall on the value-delivering action.
    """
    from datetime import UTC, datetime

    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    user = await SqlUserRepository(session).get_by_id(UserId(user_id))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.subscription_status in _INACTIVE_SUBSCRIPTION_STATUSES:
        raise HTTPException(
            status_code=402,
            detail=(
                "Twoja subskrypcja jest nieaktywna. Wybierz lub odnów plan w "
                "Ustawieniach, aby zatwierdzać zmiany."
            ),
        )
    if user.subscription_status == "trialing" and user.trial_ends_at is not None:
        ends = user.trial_ends_at
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=UTC)
        if ends < datetime.now(UTC):
            raise HTTPException(
                status_code=402,
                detail=(
                    "Okres próbny zakończył się. Wybierz plan w Ustawieniach, "
                    "aby kontynuować."
                ),
            )


@router.post("/{user_id}/recommendations/{rec_id}/approve")
async def approve_recommendation(
    user_id: str,
    rec_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Approve a recommendation and enqueue the Celery execution task."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from adcopilot.domain.recommendation import (
        NON_EXECUTABLE_KINDS,
        RecommendationId,
        RecommendationKind,
        RecommendationStatus,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await _assert_active_subscription(session, user_id)
            repo = SqlRecommendationRepository(session)
            rec = await repo.get(RecommendationId(rec_id))
            if rec is None:
                raise HTTPException(status_code=404, detail="Recommendation not found")
            if rec.status not in (RecommendationStatus.PENDING, RecommendationStatus.FAILED):
                raise HTTPException(
                    status_code=409,
                    detail=f"Recommendation is already {rec.status.value}",
                )
            if rec.kind in NON_EXECUTABLE_KINDS:
                raise HTTPException(
                    status_code=422,
                    detail="This recommendation is informational and cannot be auto-executed",
                )
            await repo.update_status(RecommendationId(rec_id), RecommendationStatus.APPROVED)
    finally:
        await engine.dispose()

    from adcopilot.interfaces.worker.tasks import execute_recommendation_task

    execute_recommendation_task.delay(rec_id)
    logger.info("recommendation.approved", user_id=user_id, rec_id=rec_id)

    return {"status": "approved", "rec_id": rec_id}


class BulkApproveRequest(BaseModel):
    recommendation_ids: list[str]


@router.post("/{user_id}/recommendations/approve-bulk")
async def approve_recommendations_bulk(
    user_id: str,
    body: BulkApproveRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, object]:
    """Approve + enqueue execution of many recommendations in one call.

    Marks each executable, owned, PENDING/FAILED recommendation APPROVED, then
    dispatches a single bulk task that runs them with per-item failure isolation.
    """
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from adcopilot.domain.recommendation import (
        NON_EXECUTABLE_KINDS,
        RecommendationId,
        RecommendationStatus,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    accepted: list[str] = []
    skipped: list[dict[str, str]] = []
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await _assert_active_subscription(session, user_id)
            repo = SqlRecommendationRepository(session)
            for rec_id in body.recommendation_ids:
                rec = await repo.get(RecommendationId(rec_id))
                if rec is None:
                    skipped.append({"rec_id": rec_id, "reason": "not_found"})
                    continue
                if rec.status not in (RecommendationStatus.PENDING, RecommendationStatus.FAILED):
                    skipped.append({"rec_id": rec_id, "reason": f"already_{rec.status.value}"})
                    continue
                if rec.kind in NON_EXECUTABLE_KINDS:
                    skipped.append({"rec_id": rec_id, "reason": "not_executable"})
                    continue
                await repo.update_status(RecommendationId(rec_id), RecommendationStatus.APPROVED)
                accepted.append(rec_id)
    finally:
        await engine.dispose()

    if accepted:
        from adcopilot.interfaces.worker.tasks import execute_recommendations_bulk_task

        execute_recommendations_bulk_task.delay(accepted)
    logger.info(
        "recommendations.bulk_approved", user_id=user_id, accepted=len(accepted), skipped=len(skipped)
    )
    return {"status": "executing", "accepted": accepted, "skipped": skipped}


@router.post("/{user_id}/recommendations/{rec_id}/decline")
async def decline_recommendation(
    user_id: str,
    rec_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Decline a recommendation without executing it."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from adcopilot.domain.recommendation import RecommendationId, RecommendationStatus
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            repo = SqlRecommendationRepository(session)
            rec = await repo.get(RecommendationId(rec_id))
            if rec is None:
                raise HTTPException(status_code=404, detail="Recommendation not found")
            if rec.status not in (RecommendationStatus.PENDING, RecommendationStatus.FAILED):
                raise HTTPException(
                    status_code=409,
                    detail=f"Recommendation is already {rec.status.value}",
                )
            await repo.update_status(RecommendationId(rec_id), RecommendationStatus.DECLINED)
    finally:
        await engine.dispose()

    logger.info("recommendation.declined", user_id=user_id, rec_id=rec_id)
    return {"status": "declined", "rec_id": rec_id}


@router.post("/{user_id}/recommendations/{rec_id}/undo")
async def undo_recommendation(
    user_id: str,
    rec_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Reverse a previously EXECUTED recommendation, within the undo window.

    Validates ownership, that the recommendation is EXECUTED, and that the
    7-day undo window has not expired, then enqueues the reversal task. The
    actual Google Ads mutation runs asynchronously; the user is notified of the
    outcome. All user-facing errors are surfaced in Polish (no silent failure).
    """
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from datetime import UTC, datetime, timedelta

    from adcopilot.application.use_cases.undo_recommendation import UNDO_WINDOW_DAYS
    from adcopilot.domain.recommendation import RecommendationId, RecommendationStatus
    from adcopilot.infrastructure.db.repositories.audit_log_repository import (
        SqlAuditLogRepository,
    )
    from adcopilot.infrastructure.db.repositories.recommendation_repository import (
        SqlRecommendationRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlRecommendationRepository(session)
            rec = await repo.get(RecommendationId(rec_id))
            if rec is None:
                raise HTTPException(status_code=404, detail="Recommendation not found")
            if rec.status != RecommendationStatus.EXECUTED:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Tylko wykonane zmiany można cofnąć "
                        f"(aktualny status: {rec.status.value})."
                    ),
                )
            audit_log = await SqlAuditLogRepository(session).get_latest_execute(
                RecommendationId(rec_id)
            )
            if audit_log is None:
                raise HTTPException(
                    status_code=409,
                    detail="Brak zapisu wykonania tej zmiany — nie ma czego cofać.",
                )
            log_ts = audit_log.created_at
            if log_ts.tzinfo is None:
                log_ts = log_ts.replace(tzinfo=UTC)
            if log_ts < datetime.now(UTC) - timedelta(days=UNDO_WINDOW_DAYS):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Okno cofania wygasło — zmianę można cofnąć w ciągu "
                        f"{UNDO_WINDOW_DAYS} dni od jej wykonania."
                    ),
                )
    finally:
        await engine.dispose()

    from adcopilot.interfaces.worker.tasks import undo_recommendation_task

    undo_recommendation_task.delay(rec_id)
    logger.info("recommendation.undo_requested", user_id=user_id, rec_id=rec_id)
    return {"status": "undoing", "rec_id": rec_id}


@router.put("/{user_id}/settings")
async def update_settings(
    user_id: str,
    body: SettingsUpdateRequest,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Update user notification and language preferences."""
    from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = SqlUserRepository(session)
            user = await repo.get_by_id(UserId(user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")

            updates: dict[str, Any] = {}
            if body.notification_hour is not None:
                if not (0 <= body.notification_hour <= 23):
                    raise HTTPException(status_code=422, detail="notification_hour must be 0-23")
                updates["notification_hour"] = body.notification_hour
            if body.language is not None:
                updates["language"] = body.language

            if updates:
                updated = dataclasses.replace(user, **updates)
                await repo.save(updated)
                await session.commit()
    finally:
        await engine.dispose()

    return {"status": "updated"}
