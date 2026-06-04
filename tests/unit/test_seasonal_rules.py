"""Tests for seasonal threshold adjustment of week-over-week detection rules."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from adcopilot.application.detection.base import DetectionContext, HistoricalStats
from adcopilot.application.detection.rules.rule_12_cpa_spike import CpaSpikeRule
from adcopilot.application.detection.rules.rule_13_conversion_rate_drop import (
    ConversionRateDropRule,
)
from adcopilot.application.detection.rules.rule_15_spend_acceleration import (
    SpendAccelerationRule,
)
from adcopilot.application.detection.seasonal import (
    seasonal_multiplier,
    seasonal_relaxed_threshold,
)
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.recommendation import RecommendationSeverity
from adcopilot.domain.snapshot import CampaignSnapshot, SnapshotId

_ACCOUNT_ID = AccountId("acct-test-1")
_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_PEAK = date(2026, 12, 1)  # salon December → multiplier 1.30
_TROUGH = date(2026, 1, 9)  # salon January → multiplier 0.80


def _account() -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=_ACCOUNT_ID,
        user_id=UserId("u1"),
        customer_id="123",
        descriptive_name="Test",
        currency="PLN",
        timezone="UTC",
        is_manager=False,
        write_enabled=True,
        connected_at=_NOW,
    )


def _campaign(snap: date, **kw) -> CampaignSnapshot:
    d = dict(
        id=SnapshotId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        snapshot_date=snap,
        campaign_id=1,
        name="Camp",
        status="ENABLED",
        channel_type="SEARCH",
        budget_micros=10_000_000,
        bidding_strategy="MANUAL_CPC",
        impressions=1000,
        clicks=200,
        cost_micros=5_000_000,
        conversions=10.0,
        conv_value=15.0,
    )
    d.update(kw)
    return CampaignSnapshot(**d)


def _ctx(snap: date, *, vertical: str | None, campaigns, prev_campaigns) -> DetectionContext:
    return DetectionContext(
        account=_account(),
        campaigns=campaigns,
        ad_groups=[],
        keywords=[],
        search_terms=[],
        ads=[],
        history=HistoricalStats(avg_cpa_micros=500_000, total_cost_micros=0, total_conversions=0.0),
        snapshot_date=snap,
        prev_campaigns=prev_campaigns,
        vertical=vertical,
        attribution_window_days=7,  # reliable, keeps severity HIGH (isolates seasonality)
    )


# --------------------------------------------------------------------------- #
# Helper
# --------------------------------------------------------------------------- #


def test_seasonal_relaxed_threshold_widens_in_peak_only():
    assert seasonal_relaxed_threshold(0.50, 1.30) == 0.65  # peak widens
    assert seasonal_relaxed_threshold(0.50, 0.80) == 0.50  # trough unchanged (not tightened)
    assert seasonal_relaxed_threshold(0.50, 1.0) == 0.50


def test_seasonal_multiplier_unknown_vertical_is_one():
    ctx = _ctx(_PEAK, vertical=None, campaigns=[], prev_campaigns=[])
    assert seasonal_multiplier(ctx) == 1.0


def test_seasonal_multiplier_uses_snapshot_month():
    ctx = _ctx(_PEAK, vertical="salon", campaigns=[], prev_campaigns=[])
    assert seasonal_multiplier(ctx) == 1.30


# --------------------------------------------------------------------------- #
# Rule 12 — CPA spike: base 0.50; salon peak threshold = 0.65
# --------------------------------------------------------------------------- #


def test_cpa_spike_suppressed_in_peak_month():
    # 55% spike: fires at base 0.50, but below the seasonal 0.65 → suppressed.
    prev = _campaign(_PEAK, cost_micros=10_000_000, conversions=10.0)  # CPA 1.0M
    curr = _campaign(_PEAK, cost_micros=15_500_000, conversions=10.0)  # CPA 1.55M (+55%)
    recs = CpaSpikeRule().detect(
        _ctx(_PEAK, vertical="salon", campaigns=[curr], prev_campaigns=[prev])
    )
    assert recs == []


def test_cpa_spike_still_fires_in_peak_for_large_spike():
    # 70% spike clears the seasonal 0.65 threshold.
    prev = _campaign(_PEAK, cost_micros=10_000_000, conversions=10.0)
    curr = _campaign(_PEAK, cost_micros=17_000_000, conversions=10.0)  # +70%
    recs = CpaSpikeRule().detect(
        _ctx(_PEAK, vertical="salon", campaigns=[curr], prev_campaigns=[prev])
    )
    assert len(recs) == 1
    assert recs[0].severity == RecommendationSeverity.HIGH
    assert recs[0].evidence["seasonal_multiplier"] == 1.3


def test_cpa_spike_55pct_fires_in_normal_month():
    # Same 55% spike, unknown vertical (multiplier 1.0) → still fires.
    prev = _campaign(_TROUGH, cost_micros=10_000_000, conversions=10.0)
    curr = _campaign(_TROUGH, cost_micros=15_500_000, conversions=10.0)
    recs = CpaSpikeRule().detect(
        _ctx(_TROUGH, vertical=None, campaigns=[curr], prev_campaigns=[prev])
    )
    assert len(recs) == 1


def test_cpa_spike_trough_not_tightened():
    # 55% spike in salon trough (mult 0.80): threshold stays at base 0.50 → fires.
    prev = _campaign(_TROUGH, cost_micros=10_000_000, conversions=10.0)
    curr = _campaign(_TROUGH, cost_micros=15_500_000, conversions=10.0)
    recs = CpaSpikeRule().detect(
        _ctx(_TROUGH, vertical="salon", campaigns=[curr], prev_campaigns=[prev])
    )
    assert len(recs) == 1


# --------------------------------------------------------------------------- #
# Rule 13 — CVR drop: base 0.25; salon peak threshold = 0.325
# --------------------------------------------------------------------------- #


def test_cvr_drop_suppressed_in_peak_month():
    # 28% drop: fires at base 0.25 but below seasonal 0.325 → suppressed.
    prev = _campaign(_PEAK, clicks=200, conversions=10.0)  # CVR 5%
    curr = _campaign(_PEAK, clicks=200, conversions=7.2)  # CVR 3.6% (−28%)
    recs = ConversionRateDropRule().detect(
        _ctx(_PEAK, vertical="salon", campaigns=[curr], prev_campaigns=[prev])
    )
    assert recs == []


def test_cvr_drop_fires_in_peak_for_large_drop():
    prev = _campaign(_PEAK, clicks=200, conversions=10.0)  # CVR 5%
    curr = _campaign(_PEAK, clicks=200, conversions=6.0)  # CVR 3% (−40%)
    recs = ConversionRateDropRule().detect(
        _ctx(_PEAK, vertical="salon", campaigns=[curr], prev_campaigns=[prev])
    )
    assert len(recs) == 1


# --------------------------------------------------------------------------- #
# Rule 15 — Spend acceleration: base 0.30; salon peak threshold = 0.39
# --------------------------------------------------------------------------- #


def test_spend_acceleration_suppressed_in_peak_month():
    # 35% growth with flat conversions: fires at base 0.30 but below seasonal 0.39.
    prev = _campaign(_PEAK, cost_micros=10_000_000, conversions=5.0)
    curr = _campaign(_PEAK, cost_micros=13_500_000, conversions=5.0)  # +35% spend, flat conv
    recs = SpendAccelerationRule().detect(
        _ctx(_PEAK, vertical="salon", campaigns=[curr], prev_campaigns=[prev])
    )
    assert recs == []


def test_spend_acceleration_fires_in_peak_for_large_jump():
    prev = _campaign(_PEAK, cost_micros=10_000_000, conversions=5.0)
    curr = _campaign(_PEAK, cost_micros=15_000_000, conversions=5.0)  # +50% spend, flat conv
    recs = SpendAccelerationRule().detect(
        _ctx(_PEAK, vertical="salon", campaigns=[curr], prev_campaigns=[prev])
    )
    assert len(recs) == 1
    assert recs[0].evidence["seasonal_multiplier"] == 1.3
