"""Repository for per-account spend-safety config (spend-safety system)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.spend_safety import SpendSafetyConfig
from adcopilot.infrastructure.db.models import SpendSafetyConfigModel


def _to_domain(m: SpendSafetyConfigModel) -> SpendSafetyConfig:
    return SpendSafetyConfig(
        account_id=str(m.account_id),
        monthly_spend_cap_micros=m.monthly_spend_cap_micros,
        daily_spend_cap_micros=m.daily_spend_cap_micros,
        per_campaign_daily_cap_micros=m.per_campaign_daily_cap_micros,
        max_budget_increase_pct=float(m.max_budget_increase_pct),
        warning_threshold_pct=float(m.warning_threshold_pct),
        auto_pause_enabled=m.auto_pause_enabled,
        currency_code=m.currency_code,
        updated_at=m.updated_at,
    )


class SpendSafetyConfigRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: str) -> SpendSafetyConfig | None:
        row = (
            await self._session.execute(
                select(SpendSafetyConfigModel).where(
                    SpendSafetyConfigModel.account_id == uuid.UUID(account_id)
                )
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def upsert(self, config: SpendSafetyConfig) -> None:
        values = {
            "account_id": uuid.UUID(config.account_id),
            "monthly_spend_cap_micros": config.monthly_spend_cap_micros,
            "daily_spend_cap_micros": config.daily_spend_cap_micros,
            "per_campaign_daily_cap_micros": config.per_campaign_daily_cap_micros,
            "max_budget_increase_pct": config.max_budget_increase_pct,
            "warning_threshold_pct": config.warning_threshold_pct,
            "auto_pause_enabled": config.auto_pause_enabled,
            "currency_code": config.currency_code,
        }
        stmt = insert(SpendSafetyConfigModel).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in values if k != "account_id"}
        stmt = stmt.on_conflict_do_update(index_elements=["account_id"], set_=update_cols)
        await self._session.execute(stmt)
