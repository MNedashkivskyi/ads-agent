"""Auto-apply settings API (Phase 3 / T3.1).

Per-account opt-in for auto-applying low-risk recommendations. Gated behind the
``auto_apply`` capability (Professional and above); STARTER receives a Polish
403. The platform-level ``AUTO_APPLY_GLOBALLY_ENABLED`` kill-switch still gates
whether anything is actually executed automatically.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from adcopilot.application.entitlements import Capability
from adcopilot.config import Settings, get_settings
from adcopilot.domain.auto_apply import AutoApplyRisk, AutoApplySettings, parse_risk
from adcopilot.interfaces.api.account_access import can_access_account
from adcopilot.interfaces.api.auth_middleware import CurrentUser
from adcopilot.interfaces.api.deps import require_capability

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["automation"])


class AutoApplySettingsResponse(BaseModel):
    enabled: bool
    max_risk: str
    max_changes_per_day: int
    globally_enabled: bool  # platform kill-switch state (informational)


class AutoApplySettingsRequest(BaseModel):
    enabled: bool = False
    max_risk: str = "LOW"
    max_changes_per_day: int = Field(default=5, ge=1, le=50)


async def _verify_account_owner(session, account_id: str, user_id: str) -> None:  # noqa: ANN001
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )

    account = await SqlGoogleAdsAccountRepository(session).get(AccountId(account_id))
    if account is None or not await can_access_account(session, account, user_id):
        raise HTTPException(status_code=404, detail="Konto Google Ads nie zostało znalezione")


@router.get(
    "/{user_id}/accounts/{account_id}/auto-apply",
    response_model=AutoApplySettingsResponse,
)
async def get_auto_apply_settings(
    user_id: str,
    account_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.AUTO_APPLY))] = None,
) -> AutoApplySettingsResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.auto_apply_settings_repository import (
        SqlAutoApplySettingsRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await _verify_account_owner(session, account_id, user_id)
            current = await SqlAutoApplySettingsRepository(session).get(account_id)
    finally:
        await engine.dispose()

    current = current or AutoApplySettings()
    return AutoApplySettingsResponse(
        enabled=current.enabled,
        max_risk=current.max_risk.value,
        max_changes_per_day=current.max_changes_per_day,
        globally_enabled=settings.AUTO_APPLY_GLOBALLY_ENABLED,
    )


@router.put(
    "/{user_id}/accounts/{account_id}/auto-apply",
    response_model=AutoApplySettingsResponse,
)
async def update_auto_apply_settings(
    user_id: str,
    account_id: str,
    body: AutoApplySettingsRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    _cap: Annotated[None, Depends(require_capability(Capability.AUTO_APPLY))] = None,
) -> AutoApplySettingsResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Brak dostępu")

    new_settings = AutoApplySettings(
        enabled=body.enabled,
        max_risk=parse_risk(body.max_risk),
        max_changes_per_day=body.max_changes_per_day,
    )

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.auto_apply_settings_repository import (
        SqlAutoApplySettingsRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            await _verify_account_owner(session, account_id, user_id)
            await SqlAutoApplySettingsRepository(session).upsert(account_id, new_settings)
    finally:
        await engine.dispose()

    logger.info(
        "auto_apply.settings_updated",
        user_id=user_id,
        account_id=account_id,
        enabled=new_settings.enabled,
        max_risk=new_settings.max_risk.value,
    )
    return AutoApplySettingsResponse(
        enabled=new_settings.enabled,
        max_risk=new_settings.max_risk.value,
        max_changes_per_day=new_settings.max_changes_per_day,
        globally_enabled=settings.AUTO_APPLY_GLOBALLY_ENABLED,
    )


# Keep AutoApplyRisk referenced for callers importing the allowed values.
ALLOWED_RISK_VALUES = tuple(r.value for r in AutoApplyRisk)
