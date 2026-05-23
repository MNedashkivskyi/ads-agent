"""WeeklyInsightRepository — persists and retrieves weekly AI insights."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.infrastructure.db.models import WeeklyInsightModel


class WeeklyInsight:
    __slots__ = (
        "id",
        "user_id",
        "account_id",
        "week_start",
        "insight_text",
        "context_snapshot",
        "created_at",
    )

    def __init__(
        self,
        id: str,
        user_id: str,
        account_id: str | None,
        week_start: date,
        insight_text: str,
        context_snapshot: dict[str, Any] | None,
        created_at: datetime,
    ) -> None:
        self.id = id
        self.user_id = user_id
        self.account_id = account_id
        self.week_start = week_start
        self.insight_text = insight_text
        self.context_snapshot = context_snapshot
        self.created_at = created_at


def _to_domain(m: WeeklyInsightModel) -> WeeklyInsight:
    return WeeklyInsight(
        id=str(m.id),
        user_id=m.user_id,
        account_id=m.account_id,
        week_start=m.week_start,
        insight_text=m.insight_text,
        context_snapshot=m.context_snapshot,
        created_at=m.created_at,
    )


class SqlWeeklyInsightRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(
        self,
        user_id: str,
        account_id: str | None,
        week_start: date,
        insight_text: str,
        context_snapshot: dict[str, Any] | None = None,
    ) -> WeeklyInsight:
        m = WeeklyInsightModel()
        m.id = uuid.uuid4()
        m.user_id = user_id
        m.account_id = account_id
        m.week_start = week_start
        m.insight_text = insight_text
        m.context_snapshot = context_snapshot
        self._session.add(m)
        await self._session.flush()
        return _to_domain(m)

    async def list_for_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[WeeklyInsight]:
        result = await self._session.execute(
            select(WeeklyInsightModel)
            .where(WeeklyInsightModel.user_id == user_id)
            .order_by(WeeklyInsightModel.week_start.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_domain(m) for m in result.scalars()]
