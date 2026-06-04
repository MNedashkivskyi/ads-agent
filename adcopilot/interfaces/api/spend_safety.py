"""Spend-safety configuration API — per-account caps + auto-pause toggle."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["spend-safety"])


class SpendSafetyRequest(BaseModel):
    monthly_spend_cap_micros: int | None = Field(default=None, ge=0)
    daily_spend_cap_micros: int | None = Field(default=None, ge=0)
    per_campaign_daily_cap_micros: int | None = Field(default=None, ge=0)
    max_budget_increase_pct: float = Field(default=50.0, gt=0, le=1000)
    warning_threshold_pct: float = Field(default=80.0, ge=0, le=100)
    auto_pause_enabled: bool = False
    currency_code: str = "PLN"


class SpendSafetyResponse(BaseModel):
    monthly_spend_cap_micros: int | None
    daily_spend_cap_micros: int | None
    per_campaign_daily_cap_micros: int | None
    max_budget_increase_pct: float
    warning_threshold_pct: float
    auto_pause_enabled: bool
    currency_code: str
    is_configured: bool


def _to_response(config) -> SpendSafetyResponse:
    return SpendSafetyResponse(
        monthly_spend_cap_micros=config.monthly_spend_cap_micros,
        daily_spend_cap_micros=config.daily_spend_cap_micros,
        per_campaign_daily_cap_micros=config.per_campaign_daily_cap_micros,
        max_budget_increase_pct=config.max_budget_increase_pct,
        warning_threshold_pct=config.warning_threshold_pct,
        auto_pause_enabled=config.auto_pause_enabled,
        currency_code=config.currency_code,
        is_configured=config.is_configured(),
    )


def _imports():
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.spend_safety_config_repository import (
        SpendSafetyConfigRepository,
    )
    from adcopilot.interfaces.api.measurement import _resolve_account

    return AsyncSession, create_async_engine, SpendSafetyConfigRepository, _resolve_account


@router.get("/{user_id}/spend-safety", response_model=SpendSafetyResponse)
async def get_spend_safety(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SpendSafetyResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    AsyncSession, create_async_engine, Repo, _resolve_account = _imports()
    from adcopilot.domain.spend_safety import SpendSafetyConfig

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            config = await Repo(session).get(str(account.id))
            if config is None:
                config = SpendSafetyConfig(account_id=str(account.id))
    finally:
        await engine.dispose()
    return _to_response(config)


class CapStatus(BaseModel):
    cap_type: str  # MONTHLY | DAILY
    cap_micros: int
    current_micros: int
    status: str  # WITHIN | WARNING | BREACH


class BreachAlert(BaseModel):
    cap_type: str
    scope: str
    severity: str
    current_micros: int
    cap_micros: int
    campaign_id: int | None
    created_at: str


class SpendSafetyStatusResponse(BaseModel):
    is_configured: bool
    auto_pause_enabled: bool
    caps: list[CapStatus]
    recent_breaches: list[BreachAlert]


@router.get("/{user_id}/spend-safety/status", response_model=SpendSafetyStatusResponse)
async def get_spend_safety_status(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SpendSafetyStatusResponse:
    """Current realized spend vs caps + recent breach alerts (for status chips)."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import calendar
    import uuid as _uuid
    from datetime import date

    from sqlalchemy import func, select

    AsyncSession, create_async_engine, Repo, _resolve_account = _imports()
    from adcopilot.domain.spend_breach import detect_spend_cap_breaches
    from adcopilot.domain.spend_safety import SpendSafetyConfig
    from adcopilot.infrastructure.db.models import AlertModel, CampaignSnapshotModel

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            config = await Repo(session).get(str(account.id)) or SpendSafetyConfig(
                account_id=str(account.id)
            )
            acct = _uuid.UUID(str(account.id))
            today = date.today()
            month_start = today.replace(day=1)
            days_in_month = calendar.monthrange(today.year, today.month)[1]

            mtd = (
                await session.execute(
                    select(func.coalesce(func.sum(CampaignSnapshotModel.cost_micros), 0)).where(
                        CampaignSnapshotModel.account_id == acct,
                        CampaignSnapshotModel.snapshot_date >= month_start,
                        CampaignSnapshotModel.snapshot_date <= today,
                    )
                )
            ).scalar_one()
            today_spend = (
                await session.execute(
                    select(func.coalesce(func.sum(CampaignSnapshotModel.cost_micros), 0)).where(
                        CampaignSnapshotModel.account_id == acct,
                        CampaignSnapshotModel.snapshot_date == today,
                    )
                )
            ).scalar_one()

            breaches = detect_spend_cap_breaches(
                config,
                account_mtd_spend_micros=int(mtd or 0),
                account_today_spend_micros=int(today_spend or 0),
                days_elapsed=today.day,
                days_in_month=days_in_month,
            )
            by_type = {b.cap_type: b.severity for b in breaches}

            caps: list[CapStatus] = []
            if config.monthly_spend_cap_micros is not None:
                caps.append(
                    CapStatus(
                        cap_type="MONTHLY",
                        cap_micros=config.monthly_spend_cap_micros,
                        current_micros=int(mtd or 0),
                        status=by_type.get("MONTHLY", "WITHIN"),
                    )
                )
            if config.daily_spend_cap_micros is not None:
                caps.append(
                    CapStatus(
                        cap_type="DAILY",
                        cap_micros=config.daily_spend_cap_micros,
                        current_micros=int(today_spend or 0),
                        status=by_type.get("DAILY", "WITHIN"),
                    )
                )

            alert_rows = (
                await session.execute(
                    select(AlertModel)
                    .where(
                        AlertModel.account_id == acct,
                        AlertModel.kind == "SPEND_CAP_BREACH",
                    )
                    .order_by(AlertModel.created_at.desc())
                    .limit(10)
                )
            ).scalars().all()
            recent = [
                BreachAlert(
                    cap_type=str(a.payload.get("cap_type", "")),
                    scope=str(a.payload.get("scope", "")),
                    severity=str(a.payload.get("severity", "")),
                    current_micros=int(a.payload.get("current_micros", 0) or 0),
                    cap_micros=int(a.payload.get("cap_micros", 0) or 0),
                    campaign_id=a.payload.get("campaign_id"),
                    created_at=a.created_at.isoformat() if a.created_at else "",
                )
                for a in alert_rows
            ]
    finally:
        await engine.dispose()

    return SpendSafetyStatusResponse(
        is_configured=config.is_configured(),
        auto_pause_enabled=config.auto_pause_enabled,
        caps=caps,
        recent_breaches=recent,
    )


@router.put("/{user_id}/spend-safety", response_model=SpendSafetyResponse)
async def put_spend_safety(
    user_id: str,
    body: SpendSafetyRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> SpendSafetyResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    AsyncSession, create_async_engine, Repo, _resolve_account = _imports()
    from adcopilot.domain.spend_safety import SpendSafetyConfig, SpendSafetyConfigError

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            try:
                config = SpendSafetyConfig(
                    account_id=str(account.id),
                    monthly_spend_cap_micros=body.monthly_spend_cap_micros,
                    daily_spend_cap_micros=body.daily_spend_cap_micros,
                    per_campaign_daily_cap_micros=body.per_campaign_daily_cap_micros,
                    max_budget_increase_pct=body.max_budget_increase_pct,
                    warning_threshold_pct=body.warning_threshold_pct,
                    auto_pause_enabled=body.auto_pause_enabled,
                    currency_code=body.currency_code,
                )
            except SpendSafetyConfigError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            await Repo(session).upsert(config)
    finally:
        await engine.dispose()
    return _to_response(config)
