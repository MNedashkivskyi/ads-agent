"""Unit tests for CheckInAggregator and render_checkin_message."""

from __future__ import annotations

import pytest

from adcopilot.application.services.checkin_aggregator import (
    CheckInAggregator,
    CheckInMetrics,
    render_checkin_message,
)


class _FakeSnapshot:
    def __init__(self, resource_name, clicks, impressions, cost_micros, conversions):
        self.resource_name = resource_name
        self.clicks = clicks
        self.impressions = impressions
        self.cost_micros = cost_micros
        self.conversions = conversions


class _FakeSnapshotRepo:
    def __init__(self, snapshots):
        self._snaps = snapshots

    async def list_by_account(self, account_id, limit=7):
        return self._snaps


@pytest.mark.asyncio
async def test_aggregates_metrics_for_matching_campaign():
    snaps = [
        _FakeSnapshot("customers/123/campaigns/1", clicks=30, impressions=600, cost_micros=60_000_000, conversions=2),
        _FakeSnapshot("customers/123/campaigns/1", clicks=20, impressions=400, cost_micros=40_000_000, conversions=1),
        _FakeSnapshot("customers/123/campaigns/2", clicks=5, impressions=100, cost_micros=5_000_000, conversions=0),
    ]
    repo = _FakeSnapshotRepo(snaps)
    aggregator = CheckInAggregator(repo)
    metrics = await aggregator.get_metrics("acc1", "customers/123/campaigns/1")

    assert metrics.clicks == 50
    assert metrics.impressions == 1000
    assert metrics.cost_pln == pytest.approx(100.0)
    assert metrics.conversions == 3
    assert metrics.ctr == pytest.approx(5.0)
    assert metrics.is_empty is False


@pytest.mark.asyncio
async def test_returns_empty_when_no_matching_campaign():
    snaps = [
        _FakeSnapshot("customers/123/campaigns/99", clicks=10, impressions=200, cost_micros=10_000_000, conversions=0),
    ]
    repo = _FakeSnapshotRepo(snaps)
    aggregator = CheckInAggregator(repo)
    metrics = await aggregator.get_metrics("acc1", "customers/123/campaigns/1")

    assert metrics.is_empty is True
    assert metrics.clicks == 0


@pytest.mark.asyncio
async def test_returns_empty_when_no_campaign_resource_name():
    repo = _FakeSnapshotRepo([])
    aggregator = CheckInAggregator(repo)
    metrics = await aggregator.get_metrics("acc1", None)
    assert metrics.is_empty is True


@pytest.mark.asyncio
async def test_handles_repo_exception_gracefully():
    class _BrokenRepo:
        async def list_by_account(self, *args, **kwargs):
            raise RuntimeError("DB error")

    aggregator = CheckInAggregator(_BrokenRepo())
    metrics = await aggregator.get_metrics("acc1", "customers/1/campaigns/1")
    assert metrics.is_empty is True


def test_performance_label_great_ctr():
    m = CheckInMetrics(clicks=100, impressions=1000, cost_pln=50.0, conversions=5, ctr=10.0, conv_rate=5.0)
    assert m.performance_label == "świetny"


def test_performance_label_low_ctr():
    m = CheckInMetrics(clicks=2, impressions=1000, cost_pln=5.0, conversions=0, ctr=0.2, conv_rate=0.0)
    assert m.performance_label == "niski CTR"


def test_render_day_3_no_data():
    m = CheckInMetrics(clicks=0, impressions=0, cost_pln=0.0, conversions=0, ctr=0.0, conv_rate=0.0)
    msg = render_checkin_message("day_3_no_data", "Sklep Testowy", m)
    assert "Sklep Testowy" in msg
    assert "3 dni" in msg


def test_render_day_7_performance_includes_all_fields():
    m = CheckInMetrics(clicks=45, impressions=900, cost_pln=90.0, conversions=3, ctr=5.0, conv_rate=6.67)
    msg = render_checkin_message("day_7_performance", "Hydraulik Kraków", m)
    assert "45" in msg
    assert "90.00 PLN" in msg
    assert "5.0%" in msg


def test_render_unknown_template_returns_fallback():
    m = CheckInMetrics(clicks=0, impressions=0, cost_pln=0.0, conversions=0, ctr=0.0, conv_rate=0.0)
    msg = render_checkin_message("nonexistent_template", "Test", m)
    assert "Test" in msg
