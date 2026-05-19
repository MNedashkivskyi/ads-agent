"""Record daily QS snapshot into keyword_qs_history for trend tracking."""

from __future__ import annotations

import uuid
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.infrastructure.db.models import KeywordSnapshotModel
from sqlalchemy import select

logger = structlog.get_logger(__name__)


async def record_qs_history(
    account_id: str,
    snapshot_date: date,
    session: AsyncSession,
) -> int:
    """Upsert today's QS values from keyword_snapshots into keyword_qs_history.

    Returns the number of rows upserted.
    """
    from adcopilot.infrastructure.db.repositories.keyword_qs_history_repository import (
        KeywordQSHistoryRepository,
    )

    result = await session.execute(
        select(KeywordSnapshotModel).where(
            KeywordSnapshotModel.account_id == uuid.UUID(account_id),
            KeywordSnapshotModel.snapshot_date == snapshot_date,
            KeywordSnapshotModel.quality_score.isnot(None),
        )
    )
    snapshots = list(result.scalars().all())

    if not snapshots:
        logger.info("record_qs_history_no_data", account_id=account_id, date=str(snapshot_date))
        return 0

    rows = [
        {
            "id": uuid.uuid4(),
            "account_id": uuid.UUID(account_id),
            "criterion_id": s.criterion_id,
            "recorded_date": snapshot_date,
            "keyword_text": s.text,
            "match_type": s.match_type,
            "quality_score": s.quality_score,
            "expected_ctr": s.expected_ctr,
            "ad_relevance": s.ad_relevance,
            "landing_page_experience": s.landing_page_experience,
        }
        for s in snapshots
    ]

    repo = KeywordQSHistoryRepository(session)
    await repo.upsert_batch(rows)
    logger.info("record_qs_history_done", account_id=account_id, count=len(rows))
    return len(rows)
