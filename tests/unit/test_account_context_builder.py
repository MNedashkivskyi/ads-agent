"""Unit tests for AccountContextBuilder."""

from __future__ import annotations

from datetime import UTC, date, datetime
from unittest.mock import AsyncMock

import pytest

from adcopilot.application.services.account_context_builder import (
    AccountContextBuilder,
    _delta_pct,
    _safe_cpa,
    _safe_cpc,
    _safe_roas,
)
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import CampaignSnapshot


def _make_campaign(name: str, cost: int, budget: int, clicks: int, conversions: float, conv_value: float, status: str = "ENABLED") -> CampaignSnapshot:
    return CampaignSnapshot(
        id="snap-1",  # type: ignore[arg-type]
        account_id=AccountId("acc-1"),
        snapshot_date=date(2026, 5, 1),
        campaign_id=1,
        name=name,
        status=status,
        channel_type="SEARCH",
        budget_micros=budget,
        bidding_strategy="TARGET_CPA",
        impressions=1000,
        clicks=clicks,
        cost_micros=cost,
        conversions=conversions,
        conv_value=conv_value,
    )


ACCOUNT = AccountId("acc-1")


def test_safe_cpc_zero_clicks() -> None:
    assert _safe_cpc(100_000, 0) == 0.0


def test_safe_cpc_normal() -> None:
    assert _safe_cpc(1_000_000, 10) == 0.1  # 1 PLN per click


def test_safe_roas_zero_cost() -> None:
    assert _safe_roas(100.0, 0) == 0.0


def test_safe_cpa_zero_conversions() -> None:
    assert _safe_cpa(1_000_000, 0) == 0.0


def test_delta_pct_basic() -> None:
    assert _delta_pct(110, 100) == 10.0
    assert _delta_pct(90, 100) == -10.0


def test_delta_pct_zero_previous() -> None:
    assert _delta_pct(50, 0) is None


@pytest.mark.asyncio
async def test_build_returns_full_context() -> None:
    campaigns = [_make_campaign("Kampania A", 5_000_000, 10_000_000, 50, 5.0, 500.0)]
    prior_campaigns = [_make_campaign("Kampania A", 4_000_000, 10_000_000, 40, 4.0, 400.0)]

    snapshot_repo = AsyncMock()
    snapshot_repo.get_latest_snapshot_date.return_value = date(2026, 5, 1)
    snapshot_repo.get_campaigns_by_date.side_effect = [campaigns, prior_campaigns]

    rec_repo = AsyncMock()
    rec_repo.list_pending.return_value = []

    audit_log_repo = AsyncMock()
    audit_log_repo.list_recent_executes.return_value = []

    builder = AccountContextBuilder(snapshot_repo, rec_repo, audit_log_repo)
    ctx = await builder.build(ACCOUNT)

    assert ctx["account_id"] == "acc-1"
    assert ctx["summary"]["total_spend_pln"] == 5.0
    assert ctx["summary"]["total_clicks"] == 50
    assert ctx["summary"]["total_conversions"] == 5.0
    assert ctx["summary"]["active_campaigns"] == 1
    assert len(ctx["top_campaigns"]) == 1
    assert ctx["top_campaigns"][0]["name"] == "Kampania A"
    assert ctx["week_over_week_deltas"]["cost_pct"] == 25.0


@pytest.mark.asyncio
async def test_build_empty_context_when_no_snapshot() -> None:
    snapshot_repo = AsyncMock()
    snapshot_repo.get_latest_snapshot_date.return_value = None

    builder = AccountContextBuilder(snapshot_repo, AsyncMock(), AsyncMock())
    ctx = await builder.build(ACCOUNT)

    assert ctx["summary"] is None
    assert ctx["snapshot_date"] is None
    assert "note" in ctx


@pytest.mark.asyncio
async def test_build_includes_pending_alerts() -> None:
    from adcopilot.domain.recommendation import (
        Recommendation,
        RecommendationId,
        RecommendationKind,
        RecommendationSeverity,
        RecommendationStatus,
    )

    alert = Recommendation(
        id=RecommendationId("rec-1"),
        account_id=ACCOUNT,
        kind=RecommendationKind.CPA_SPIKE,
        severity=RecommendationSeverity.HIGH,
        target={"account_id": "acc-1"},
        payload={},
        evidence={},
        estimated_monthly_savings_micros=0,
        created_at=datetime.now(UTC),
        status=RecommendationStatus.PENDING,
    )

    snapshot_repo = AsyncMock()
    snapshot_repo.get_latest_snapshot_date.return_value = date(2026, 5, 1)
    snapshot_repo.get_campaigns_by_date.side_effect = [[], []]
    rec_repo = AsyncMock()
    rec_repo.list_pending.return_value = [alert]
    audit_log_repo = AsyncMock()
    audit_log_repo.list_recent_executes.return_value = []

    builder = AccountContextBuilder(snapshot_repo, rec_repo, audit_log_repo)
    ctx = await builder.build(ACCOUNT)

    assert len(ctx["active_alerts"]) == 1
    assert ctx["active_alerts"][0]["kind"] == "CPA_SPIKE"
