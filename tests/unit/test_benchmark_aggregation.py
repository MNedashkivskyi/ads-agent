"""Tests for VerticalBenchmarkSnapshot aggregation and AggregateBenchmarksUseCase."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.domain.benchmarking import AccountMetrics, VerticalBenchmarkSnapshot

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_accounts(
    n: int,
    cpa_micros: int = 1_000_000,
    ctr: float = 0.05,
    conversion_rate: float = 0.03,
    monthly_spend_micros: int = 10_000_000,
) -> list[AccountMetrics]:
    return [
        AccountMetrics(
            account_id=f"acct-{i}",
            cpa_micros=cpa_micros + i * 100_000,
            ctr=ctr,
            conversion_rate=conversion_rate,
            monthly_spend_micros=monthly_spend_micros,
        )
        for i in range(n)
    ]


_NOW = datetime(2026, 4, 22, 5, 0, 0, tzinfo=UTC)
_WEEK = date(2026, 4, 20)  # Monday


# ---------------------------------------------------------------------------
# VerticalBenchmarkSnapshot.aggregate()
# ---------------------------------------------------------------------------


def test_aggregate_returns_none_below_min_accounts() -> None:
    accounts = _make_accounts(4)
    result = VerticalBenchmarkSnapshot.aggregate(
        vertical="salon",
        city_tier=1,
        snapshot_week=_WEEK,
        accounts=accounts,
        created_at=_NOW,
    )
    assert result is None


def test_aggregate_returns_none_when_all_cpa_zero() -> None:
    accounts = [
        AccountMetrics(
            account_id=f"acct-{i}",
            cpa_micros=0,
            ctr=0.05,
            conversion_rate=0.03,
            monthly_spend_micros=5_000_000,
        )
        for i in range(6)
    ]
    result = VerticalBenchmarkSnapshot.aggregate(
        vertical="salon",
        city_tier=1,
        snapshot_week=_WEEK,
        accounts=accounts,
        created_at=_NOW,
    )
    assert result is None


def test_aggregate_returns_snapshot_for_5_accounts() -> None:
    accounts = _make_accounts(5)
    result = VerticalBenchmarkSnapshot.aggregate(
        vertical="legal",
        city_tier=2,
        snapshot_week=_WEEK,
        accounts=accounts,
        created_at=_NOW,
    )
    assert result is not None
    assert result.vertical == "legal"
    assert result.city_tier == 2
    assert result.snapshot_week == _WEEK
    assert result.account_count == 5


def test_aggregate_percentiles_order() -> None:
    # CPAs: 1M, 2M, 3M, 4M, 5M (sorted)
    accounts = [
        AccountMetrics(
            account_id=f"a{i}",
            cpa_micros=(i + 1) * 1_000_000,
            ctr=0.05,
            conversion_rate=0.03,
            monthly_spend_micros=10_000_000,
        )
        for i in range(5)
    ]
    snap = VerticalBenchmarkSnapshot.aggregate(
        vertical="medical",
        city_tier=1,
        snapshot_week=_WEEK,
        accounts=accounts,
        created_at=_NOW,
    )
    assert snap is not None
    assert snap.p25_cpa_micros <= snap.median_cpa_micros <= snap.p75_cpa_micros


def test_aggregate_avg_ctr_and_conversion_rate() -> None:
    accounts = _make_accounts(5, ctr=0.10, conversion_rate=0.05)
    snap = VerticalBenchmarkSnapshot.aggregate(
        vertical="ecommerce",
        city_tier=1,
        snapshot_week=_WEEK,
        accounts=accounts,
        created_at=_NOW,
    )
    assert snap is not None
    assert abs(snap.avg_ctr - 0.10) < 1e-6
    assert abs(snap.avg_conversion_rate - 0.05) < 1e-6


def test_aggregate_ignores_zero_cpa_accounts_in_percentiles() -> None:
    """Zero-CPA accounts (no conversions) are excluded from percentile computation."""
    non_zero = _make_accounts(5, cpa_micros=2_000_000)
    zero = AccountMetrics(
        account_id="zero",
        cpa_micros=0,
        ctr=0.01,
        conversion_rate=0.0,
        monthly_spend_micros=1_000_000,
    )
    snap = VerticalBenchmarkSnapshot.aggregate(
        vertical="restaurant",
        city_tier=3,
        snapshot_week=_WEEK,
        accounts=[*non_zero, zero],
        created_at=_NOW,
    )
    assert snap is not None
    # avg_cpa_micros computed only from non-zero CPAs
    assert snap.avg_cpa_micros > 0


def test_aggregate_id_is_unique_per_call() -> None:
    accounts = _make_accounts(5)
    snap1 = VerticalBenchmarkSnapshot.aggregate("salon", 1, _WEEK, accounts, _NOW)
    snap2 = VerticalBenchmarkSnapshot.aggregate("salon", 1, _WEEK, accounts, _NOW)
    assert snap1 is not None and snap2 is not None
    assert snap1.id != snap2.id


# ---------------------------------------------------------------------------
# AggregateBenchmarksUseCase
# ---------------------------------------------------------------------------


def _make_summary(
    account_id: str,
    vertical: str,
    city: str = "Warszawa",
    cpa_micros: int = 1_000_000,
    ctr: float = 0.05,
    conversion_rate: float = 0.03,
    monthly_spend_micros: int = 10_000_000,
) -> dict[str, object]:
    return {
        "account_id": account_id,
        "vertical": vertical,
        "city": city,
        "cpa_micros": cpa_micros,
        "ctr": ctr,
        "conversion_rate": conversion_rate,
        "monthly_spend_micros": monthly_spend_micros,
    }


@pytest.mark.asyncio
async def test_use_case_saves_when_enough_accounts() -> None:
    from adcopilot.application.use_cases.aggregate_benchmarks import AggregateBenchmarksUseCase

    summaries = [
        _make_summary(f"a{i}", "salon", cpa_micros=1_000_000 + i * 50_000) for i in range(6)
    ]

    provider = MagicMock()
    provider.list_account_summaries = AsyncMock(return_value=summaries)

    repo = MagicMock()
    repo.exists_for_week = AsyncMock(return_value=False)
    repo.save = AsyncMock()

    uc = AggregateBenchmarksUseCase(account_summary_provider=provider, benchmark_repo=repo)
    result = await uc.run(reference_date=date(2026, 4, 22))

    assert result["saved"] == 1
    assert result["skipped"] == 0
    repo.save.assert_awaited_once()


@pytest.mark.asyncio
async def test_use_case_skips_when_too_few_accounts() -> None:
    from adcopilot.application.use_cases.aggregate_benchmarks import AggregateBenchmarksUseCase

    summaries = [_make_summary(f"a{i}", "salon") for i in range(3)]

    provider = MagicMock()
    provider.list_account_summaries = AsyncMock(return_value=summaries)

    repo = MagicMock()
    repo.exists_for_week = AsyncMock(return_value=False)
    repo.save = AsyncMock()

    uc = AggregateBenchmarksUseCase(account_summary_provider=provider, benchmark_repo=repo)
    result = await uc.run(reference_date=date(2026, 4, 22))

    assert result["saved"] == 0
    assert result["skipped"] == 1
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_use_case_skips_existing_snapshot() -> None:
    from adcopilot.application.use_cases.aggregate_benchmarks import AggregateBenchmarksUseCase

    summaries = [_make_summary(f"a{i}", "legal") for i in range(6)]

    provider = MagicMock()
    provider.list_account_summaries = AsyncMock(return_value=summaries)

    repo = MagicMock()
    repo.exists_for_week = AsyncMock(return_value=True)  # already exists
    repo.save = AsyncMock()

    uc = AggregateBenchmarksUseCase(account_summary_provider=provider, benchmark_repo=repo)
    result = await uc.run(reference_date=date(2026, 4, 22))

    assert result["saved"] == 0
    assert result["skipped"] == 1
    repo.save.assert_not_awaited()


@pytest.mark.asyncio
async def test_use_case_groups_by_vertical_and_city_tier() -> None:
    from adcopilot.application.use_cases.aggregate_benchmarks import AggregateBenchmarksUseCase

    # 6 salon accounts in Warszawa (tier 1) + 6 legal accounts in Kraków (tier 1)
    summaries = [
        *[_make_summary(f"s{i}", "salon", city="Warszawa") for i in range(6)],
        *[_make_summary(f"l{i}", "legal", city="Kraków") for i in range(6)],
    ]

    provider = MagicMock()
    provider.list_account_summaries = AsyncMock(return_value=summaries)

    repo = MagicMock()
    repo.exists_for_week = AsyncMock(return_value=False)
    repo.save = AsyncMock()

    uc = AggregateBenchmarksUseCase(account_summary_provider=provider, benchmark_repo=repo)
    result = await uc.run(reference_date=date(2026, 4, 22))

    assert result["saved"] == 2
    assert repo.save.await_count == 2
