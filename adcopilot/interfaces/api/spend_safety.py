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
