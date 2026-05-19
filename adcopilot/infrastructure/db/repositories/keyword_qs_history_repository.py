"""Repository for keyword_qs_history table."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.infrastructure.db.models import KeywordQSHistoryModel


class KeywordQSHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_batch(self, rows: list[dict]) -> None:
        if not rows:
            return
        stmt = insert(KeywordQSHistoryModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_keyword_qs_history_account_criterion_date",
            set_={
                "quality_score": stmt.excluded.quality_score,
                "expected_ctr": stmt.excluded.expected_ctr,
                "ad_relevance": stmt.excluded.ad_relevance,
                "landing_page_experience": stmt.excluded.landing_page_experience,
            },
        )
        await self._session.execute(stmt)

    async def get_history_for_keyword(
        self,
        account_id: str,
        criterion_id: int,
        limit: int = 30,
    ) -> list[KeywordQSHistoryModel]:
        result = await self._session.execute(
            select(KeywordQSHistoryModel)
            .where(
                KeywordQSHistoryModel.account_id == uuid.UUID(account_id),
                KeywordQSHistoryModel.criterion_id == criterion_id,
            )
            .order_by(KeywordQSHistoryModel.recorded_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_per_keyword(
        self,
        account_id: str,
        limit: int = 50,
    ) -> list[KeywordQSHistoryModel]:
        """Return the most-recent history row per keyword, ordered by recorded_date desc."""
        from sqlalchemy import func, over
        from sqlalchemy.orm import aliased

        subq = (
            select(
                KeywordQSHistoryModel,
                func.row_number()
                .over(
                    partition_by=KeywordQSHistoryModel.criterion_id,
                    order_by=KeywordQSHistoryModel.recorded_date.desc(),
                )
                .label("rn"),
            )
            .where(KeywordQSHistoryModel.account_id == uuid.UUID(account_id))
            .subquery()
        )
        result = await self._session.execute(
            select(KeywordQSHistoryModel)
            .join(subq, KeywordQSHistoryModel.id == subq.c.id)
            .where(subq.c.rn == 1)
            .order_by(KeywordQSHistoryModel.recorded_date.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
