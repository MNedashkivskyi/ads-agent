"""Tests for PMax detection rules — Phase 6 Task 6.4."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

from adcopilot.application.detection.rules.rule_49_pmax_low_roas import PMaxLowRoasRule
from adcopilot.application.detection.rules.rule_50_pmax_asset_disapproved import (
    PMaxAssetDisapprovedRule,
)
from adcopilot.domain.recommendation import RecommendationKind, RecommendationSeverity
from adcopilot.domain.snapshot import CampaignSnapshot


def _make_ctx(campaigns: list[CampaignSnapshot]) -> MagicMock:
    ctx = MagicMock()
    ctx.account.id = "acc-1"
    ctx.campaigns = campaigns
    return ctx


def _make_pmax_campaign(
    campaign_id: int = 1,
    cost_micros: int = 50_000_000,  # 50 PLN
    conv_value: float = 0.0,
    impressions: int = 1000,
    status: str = "ENABLED",
    channel_type: str = "PERFORMANCE_MAX",
) -> CampaignSnapshot:
    return CampaignSnapshot(
        id="snap-1",
        account_id="acc-1",
        snapshot_date=date(2026, 5, 19),
        campaign_id=campaign_id,
        name=f"PMax Campaign {campaign_id}",
        status=status,
        channel_type=channel_type,
        budget_micros=100_000_000,
        bidding_strategy="MAXIMIZE_CONVERSIONS",
        impressions=impressions,
        clicks=10,
        cost_micros=cost_micros,
        conversions=0.0,
        conv_value=conv_value,
    )


# ---------------------------------------------------------------------------
# PMaxLowRoasRule
# ---------------------------------------------------------------------------


class TestPMaxLowRoasRule:
    def test_fires_for_zero_conv_value(self):
        rule = PMaxLowRoasRule()
        campaign = _make_pmax_campaign(cost_micros=50_000_000, conv_value=0.0)
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.PMAX_LOW_ROAS
        assert recs[0].severity == RecommendationSeverity.HIGH

    def test_fires_for_low_roas(self):
        # ROAS = 50 PLN revenue / 50 PLN cost = 1.0 < 2.0 target
        rule = PMaxLowRoasRule()
        campaign = _make_pmax_campaign(cost_micros=50_000_000, conv_value=50.0)
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 1
        assert recs[0].payload["roas"] == 1.0

    def test_does_not_fire_for_good_roas(self):
        # ROAS = 200 PLN / 50 PLN = 4.0 >= 2.0 target
        rule = PMaxLowRoasRule()
        campaign = _make_pmax_campaign(cost_micros=50_000_000, conv_value=200.0)
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_does_not_fire_for_non_pmax(self):
        rule = PMaxLowRoasRule()
        campaign = _make_pmax_campaign(
            cost_micros=50_000_000, conv_value=0.0, channel_type="SEARCH"
        )
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_does_not_fire_below_min_cost(self):
        rule = PMaxLowRoasRule()
        campaign = _make_pmax_campaign(
            cost_micros=500_000, conv_value=0.0
        )  # 0.5 PLN < 10 PLN threshold
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_does_not_fire_for_removed_status(self):
        rule = PMaxLowRoasRule()
        campaign = _make_pmax_campaign(cost_micros=50_000_000, conv_value=0.0, status="REMOVED")
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_evidence_contains_campaign_name(self):
        rule = PMaxLowRoasRule()
        campaign = _make_pmax_campaign(cost_micros=50_000_000, conv_value=0.0)
        recs = rule.detect(_make_ctx([campaign]))
        assert "campaign_name" in recs[0].evidence

    def test_multiple_pmax_campaigns(self):
        rule = PMaxLowRoasRule()
        bad1 = _make_pmax_campaign(campaign_id=1, cost_micros=50_000_000, conv_value=0.0)
        bad2 = _make_pmax_campaign(campaign_id=2, cost_micros=50_000_000, conv_value=10.0)
        good = _make_pmax_campaign(campaign_id=3, cost_micros=50_000_000, conv_value=300.0)
        recs = rule.detect(_make_ctx([bad1, bad2, good]))
        assert len(recs) == 2


# ---------------------------------------------------------------------------
# PMaxAssetDisapprovedRule
# ---------------------------------------------------------------------------


class TestPMaxAssetDisapprovedRule:
    def test_fires_for_enabled_pmax_with_spend_but_no_impressions(self):
        rule = PMaxAssetDisapprovedRule()
        campaign = _make_pmax_campaign(
            cost_micros=5_000_000,  # 5 PLN > 1 PLN threshold
            impressions=0,
            status="ENABLED",
        )
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.PMAX_ASSET_DISAPPROVED
        assert recs[0].severity == RecommendationSeverity.CRITICAL

    def test_does_not_fire_when_impressions_exist(self):
        rule = PMaxAssetDisapprovedRule()
        campaign = _make_pmax_campaign(cost_micros=5_000_000, impressions=500, status="ENABLED")
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_does_not_fire_for_non_pmax(self):
        rule = PMaxAssetDisapprovedRule()
        campaign = _make_pmax_campaign(
            cost_micros=5_000_000, impressions=0, status="ENABLED", channel_type="SEARCH"
        )
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_does_not_fire_for_paused(self):
        rule = PMaxAssetDisapprovedRule()
        campaign = _make_pmax_campaign(cost_micros=5_000_000, impressions=0, status="PAUSED")
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_does_not_fire_below_min_cost(self):
        rule = PMaxAssetDisapprovedRule()
        campaign = _make_pmax_campaign(
            cost_micros=500_000,
            impressions=0,
            status="ENABLED",  # 0.5 PLN < 1 PLN
        )
        recs = rule.detect(_make_ctx([campaign]))
        assert len(recs) == 0

    def test_evidence_contains_diagnosis(self):
        rule = PMaxAssetDisapprovedRule()
        campaign = _make_pmax_campaign(cost_micros=5_000_000, impressions=0, status="ENABLED")
        recs = rule.detect(_make_ctx([campaign]))
        assert "diagnosis" in recs[0].evidence
        assert "PMax" in recs[0].evidence["diagnosis"]


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_pmax_kinds_in_recommendation_kind():
    assert RecommendationKind.PMAX_LOW_ROAS.value == "PMAX_LOW_ROAS"
    assert RecommendationKind.PMAX_ASSET_DISAPPROVED.value == "PMAX_ASSET_DISAPPROVED"


def test_pmax_kinds_in_non_executable():
    from adcopilot.domain.recommendation import NON_EXECUTABLE_KINDS

    assert RecommendationKind.PMAX_LOW_ROAS in NON_EXECUTABLE_KINDS
    assert RecommendationKind.PMAX_ASSET_DISAPPROVED in NON_EXECUTABLE_KINDS


def test_pmax_rules_registered_in_registry():
    from unittest.mock import MagicMock

    from adcopilot.application.detection.registry import build_rule_engine

    mock_rec_repo = MagicMock()
    mock_snooze_repo = MagicMock()
    engine = build_rule_engine(mock_rec_repo, mock_snooze_repo)

    kinds = {type(r).kind for r in engine._rules if hasattr(type(r), "kind")}
    assert RecommendationKind.PMAX_LOW_ROAS in kinds
    assert RecommendationKind.PMAX_ASSET_DISAPPROVED in kinds
