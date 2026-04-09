"""SQLAlchemy implementation of DigestSentLogRepository."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import UserId
from adcopilot.infrastructure.db.models import DigestSentLogModel


class SqlDigestSentLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def was_sent_today(self, user_id: UserId, today: date) -> bool:
        result = await self._session.execute(
            select(DigestSentLogModel).where(
                DigestSentLogModel.user_id == uuid.UUID(user_id),
                DigestSentLogModel.sent_date == today,
            )
        )
        return result.scalar_one_or_none() is not None

    async def record(self, user_id: UserId, sent_date: date, rec_ids: list[str]) -> None:
        log = DigestSentLogModel()
        log.id = uuid.uuid4()
        log.user_id = uuid.UUID(user_id)
        log.sent_date = sent_date
        log.recommendation_ids = rec_ids
        self._session.add(log)
        await self._session.flush()
