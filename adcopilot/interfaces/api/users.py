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
    status: str
    estimated_monthly_savings_micros: int
    explanation: str | None
    created_at: str


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
    last_snapshot_date: str | None


class SyncStatusResponse(BaseModel):
    syncing: bool  # True if any account has no snapshots yet
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

    from sqlalchemy import func, select

    from adcopilot.infrastructure.db.models import CampaignSnapshotModel, GoogleAdsAccountModel

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
                    syncing=False, accounts=[], estimated_seconds_remaining=None
                )

            statuses: list[AccountSyncStatus] = []
            any_syncing = False

            for acct in accounts:
                snap_result = await session.execute(
                    select(func.max(CampaignSnapshotModel.snapshot_date)).where(
                        CampaignSnapshotModel.account_id == acct.id
                    )
                )
                last_date = snap_result.scalar_one_or_none()
                has_snapshots = last_date is not None

                if not has_snapshots:
                    any_syncing = True

                statuses.append(
                    AccountSyncStatus(
                        account_id=str(acct.id),
                        customer_id=acct.customer_id,
                        descriptive_name=acct.descriptive_name or "",
                        connected_at=acct.connected_at.isoformat()
                        if acct.connected_at
                        else "",
                        has_snapshots=has_snapshots,
                        last_snapshot_date=str(last_date) if last_date else None,
                    )
                )

            # Rough ETA: initial snapshot typically takes 1-3 minutes per account.
            # Estimate ~120s per account still syncing.
            pending_count = sum(1 for s in statuses if not s.has_snapshots)
            estimated = pending_count * 120 if any_syncing else None

            return SyncStatusResponse(
                syncing=any_syncing,
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
    settings: Annotated[Settings, Depends(get_settings)],
) -> StatsResponse:
    """Get cumulative savings and recommendation counts for the user."""

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
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[RecommendationResponse]:
    """List all recommendations across the user's accounts."""
    import uuid as uuid_mod

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
                .where(RecommendationModel.account_id.in_(account_uuids))
                .order_by(RecommendationModel.created_at.desc())
            )
            recs = result.scalars().all()
    finally:
        await engine.dispose()

    return [
        RecommendationResponse(
            id=str(r.id),
            account_id=str(r.account_id),
            kind=r.kind,
            severity=r.severity,
            status=r.status,
            estimated_monthly_savings_micros=r.estimated_monthly_savings_micros,
            explanation=r.explanation,
            created_at=r.created_at.isoformat(),
        )
        for r in recs
    ]


@router.get("/{user_id}/audit-log", response_model=list[AuditLogResponse])
async def list_audit_log(
    user_id: str,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[AuditLogResponse]:
    """List audit log entries for the user's accounts (last 90 days)."""
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
            if rec.status != RecommendationStatus.PENDING:
                raise HTTPException(
                    status_code=409,
                    detail=f"Recommendation is already {rec.status.value}",
                )
            await repo.update_status(RecommendationId(rec_id), RecommendationStatus.APPROVED)
    finally:
        await engine.dispose()

    from adcopilot.interfaces.worker.tasks import execute_recommendation_task

    execute_recommendation_task.delay(rec_id)
    logger.info("recommendation.approved", user_id=user_id, rec_id=rec_id)

    return {"status": "approved", "rec_id": rec_id}


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
            if rec.status != RecommendationStatus.PENDING:
                raise HTTPException(
                    status_code=409,
                    detail=f"Recommendation is already {rec.status.value}",
                )
            await repo.update_status(RecommendationId(rec_id), RecommendationStatus.DECLINED)
    finally:
        await engine.dispose()

    logger.info("recommendation.declined", user_id=user_id, rec_id=rec_id)
    return {"status": "declined", "rec_id": rec_id}


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
