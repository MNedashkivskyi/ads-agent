"""SQLAlchemy implementation of SnoozeRepository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import Recommendation
from adcopilot.infrastructure.db.models import RecommendationSnoozeModel


class SqlSnoozeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_snooze(self, rec: Recommendation, snoozed_until: datetime) -> None:
        snooze = RecommendationSnoozeModel()
        snooze.id = uuid.uuid4()
        snooze.recommendation_id = uuid.UUID(rec.id)
        snooze.account_id = uuid.UUID(rec.account_id)
        snooze.kind = rec.kind.value
        snooze.target_hash = rec.target_hash
        snooze.snoozed_until = snoozed_until
        self._session.add(snooze)
        await self._session.flush()

    async def get_active_snooze_keys(
        self, account_id: AccountId, now: datetime
    ) -> set[tuple[str, str]]:
        result = await self._session.execute(
            select(RecommendationSnoozeModel).where(
                RecommendationSnoozeModel.account_id == uuid.UUID(account_id),
                RecommendationSnoozeModel.snoozed_until > now,
            )
        )
        return {(m.kind, m.target_hash) for m in result.scalars().all()}
