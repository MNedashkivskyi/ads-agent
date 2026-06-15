"""Repository for per-account auto-apply settings (Phase 3 / T3.1)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.auto_apply import AutoApplySettings, parse_risk
from adcopilot.infrastructure.db.models import AutoApplySettingsModel


def _to_domain(m: AutoApplySettingsModel) -> AutoApplySettings:
    return AutoApplySettings(
        enabled=m.enabled,
        max_risk=parse_risk(m.max_risk),
        max_changes_per_day=m.max_changes_per_day,
    )


class SqlAutoApplySettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, account_id: str) -> AutoApplySettings | None:
        row = (
            await self._session.execute(
                select(AutoApplySettingsModel).where(
                    AutoApplySettingsModel.account_id == uuid.UUID(account_id)
                )
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def upsert(self, account_id: str, settings: AutoApplySettings) -> None:
        stmt = (
            insert(AutoApplySettingsModel)
            .values(
                account_id=uuid.UUID(account_id),
                enabled=settings.enabled,
                max_risk=settings.max_risk.value,
                max_changes_per_day=settings.max_changes_per_day,
            )
            .on_conflict_do_update(
                index_elements=[AutoApplySettingsModel.account_id],
                set_={
                    "enabled": settings.enabled,
                    "max_risk": settings.max_risk.value,
                    "max_changes_per_day": settings.max_changes_per_day,
                },
            )
        )
        await self._session.execute(stmt)
