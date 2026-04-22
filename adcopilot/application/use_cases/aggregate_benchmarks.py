"""Use case: aggregate anonymized performance data across accounts into vertical benchmarks."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from adcopilot.domain.benchmarking import AccountMetrics, VerticalBenchmarkSnapshot
from adcopilot.domain.polish_market.city_tiers import classify_city


class BenchmarkRepository(Protocol):
    async def save(self, snapshot: VerticalBenchmarkSnapshot) -> None: ...
    async def exists_for_week(self, vertical: str, city_tier: int, week: date) -> bool: ...


class AccountSummaryProvider(Protocol):
    """Provides aggregated account-level metrics for a given week."""

    async def list_account_summaries(
        self, week_start: date
    ) -> list[dict[str, object]]:
        """Return list of dicts with keys: account_id, vertical, city, cpa_micros,
        ctr, conversion_rate, monthly_spend_micros."""
        ...


def _iso_week_monday(d: date) -> date:
    """Return the Monday of the ISO week containing *d*."""
    return d - timedelta(days=d.weekday())


class AggregateBenchmarksUseCase:
    """Aggregate anonymized performance metrics across accounts by vertical × city_tier.

    Only stores benchmarks when the cohort has ≥5 accounts (privacy requirement).
    """

    def __init__(
        self,
        account_summary_provider: AccountSummaryProvider,
        benchmark_repo: BenchmarkRepository,
    ) -> None:
        self._provider = account_summary_provider
        self._repo = benchmark_repo

    async def run(self, reference_date: date | None = None) -> dict[str, int]:
        """Aggregate benchmarks for the current/given week. Returns counts."""
        ref = reference_date or date.today()
        week_start = _iso_week_monday(ref)
        now = datetime.now(UTC)

        summaries = await self._provider.list_account_summaries(week_start)

        # Group by (vertical, city_tier)
        groups: dict[tuple[str, int], list[AccountMetrics]] = {}
        for s in summaries:
            vertical = str(s.get("vertical") or "generic")
            city = str(s.get("city") or "")
            tier = classify_city(city)
            key = (vertical, tier)
            groups.setdefault(key, []).append(
                AccountMetrics(
                    account_id=str(s["account_id"]),
                    cpa_micros=int(s.get("cpa_micros") or 0),
                    ctr=float(s.get("ctr") or 0.0),
                    conversion_rate=float(s.get("conversion_rate") or 0.0),
                    monthly_spend_micros=int(s.get("monthly_spend_micros") or 0),
                )
            )

        saved = 0
        skipped = 0
        for (vertical, tier), accounts in groups.items():
            if await self._repo.exists_for_week(vertical, tier, week_start):
                skipped += 1
                continue

            snapshot = VerticalBenchmarkSnapshot.aggregate(
                vertical=vertical,
                city_tier=tier,
                snapshot_week=week_start,
                accounts=accounts,
                created_at=now,
            )
            if snapshot is None:
                skipped += 1
                continue

            await self._repo.save(snapshot)
            saved += 1

        return {"saved": saved, "skipped": skipped}
