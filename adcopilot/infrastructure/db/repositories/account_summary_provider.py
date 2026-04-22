"""SQL implementation of AccountSummaryProvider — aggregates per-account metrics."""

from __future__ import annotations

from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


class SqlAccountSummaryProvider:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_account_summaries(
        self, week_start: date
    ) -> list[dict[str, object]]:
        """Return aggregated account metrics for the 7-day window starting at week_start."""
        week_end = week_start + timedelta(days=6)
        result = await self._session.execute(
            sa.text(
                """
                SELECT
                    cs.account_id::text                          AS account_id,
                    ga.vertical                                  AS vertical,
                    ga.timezone                                  AS city,
                    SUM(cs.cost_micros)                          AS monthly_spend_micros,
                    CASE WHEN SUM(cs.impressions) > 0
                         THEN SUM(cs.clicks)::float / SUM(cs.impressions)
                         ELSE 0.0 END                            AS ctr,
                    CASE WHEN SUM(cs.clicks) > 0
                         THEN SUM(cs.conversions) / SUM(cs.clicks)
                         ELSE 0.0 END                            AS conversion_rate,
                    CASE WHEN SUM(cs.conversions) > 0
                         THEN SUM(cs.cost_micros) / SUM(cs.conversions)
                         ELSE 0 END                              AS cpa_micros
                FROM campaign_snapshots cs
                JOIN google_ads_accounts ga ON ga.id = cs.account_id
                WHERE cs.snapshot_date BETWEEN :week_start AND :week_end
                  AND ga.vertical IS NOT NULL
                GROUP BY cs.account_id, ga.vertical, ga.timezone
                """
            ),
            {"week_start": week_start, "week_end": week_end},
        )
        rows = result.mappings().all()
        return [dict(row) for row in rows]
