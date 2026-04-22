"""SQL implementation of BenchmarkRepository."""

from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.benchmarking import VerticalBenchmarkSnapshot


class SqlBenchmarkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, snapshot: VerticalBenchmarkSnapshot) -> None:
        await self._session.execute(
            sa.text(
                """
                INSERT INTO vertical_benchmark_snapshots
                    (id, vertical, city_tier, snapshot_week, account_count,
                     avg_cpa_micros, median_cpa_micros, p25_cpa_micros, p75_cpa_micros,
                     avg_ctr, avg_conversion_rate, avg_monthly_spend_micros, created_at)
                VALUES
                    (:id, :vertical, :city_tier, :snapshot_week, :account_count,
                     :avg_cpa_micros, :median_cpa_micros, :p25_cpa_micros, :p75_cpa_micros,
                     :avg_ctr, :avg_conversion_rate, :avg_monthly_spend_micros, :created_at)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": uuid.UUID(snapshot.id),
                "vertical": snapshot.vertical,
                "city_tier": snapshot.city_tier,
                "snapshot_week": snapshot.snapshot_week,
                "account_count": snapshot.account_count,
                "avg_cpa_micros": snapshot.avg_cpa_micros,
                "median_cpa_micros": snapshot.median_cpa_micros,
                "p25_cpa_micros": snapshot.p25_cpa_micros,
                "p75_cpa_micros": snapshot.p75_cpa_micros,
                "avg_ctr": snapshot.avg_ctr,
                "avg_conversion_rate": snapshot.avg_conversion_rate,
                "avg_monthly_spend_micros": snapshot.avg_monthly_spend_micros,
                "created_at": snapshot.created_at,
            },
        )

    async def exists_for_week(self, vertical: str, city_tier: int, week: date) -> bool:
        result = await self._session.execute(
            sa.text(
                """
                SELECT 1 FROM vertical_benchmark_snapshots
                WHERE vertical = :vertical
                  AND city_tier = :city_tier
                  AND snapshot_week = :week
                LIMIT 1
                """
            ),
            {"vertical": vertical, "city_tier": city_tier, "week": week},
        )
        return result.first() is not None
