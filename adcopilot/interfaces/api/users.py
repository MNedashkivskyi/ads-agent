"""User data endpoints."""

from __future__ import annotations

import dataclasses
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.domain.entities import UserId

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])


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


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{user_id}/accounts", response_model=list[AccountResponse])
async def list_accounts(
    user_id: str,
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
                select(RecommendationModel.status, func.count()).where(
                    RecommendationModel.account_id.in_(account_uuids)
                ).group_by(RecommendationModel.status)
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
    from datetime import UTC, datetime, timedelta

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
