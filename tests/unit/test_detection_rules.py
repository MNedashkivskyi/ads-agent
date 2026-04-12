from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest

from adcopilot.application.detection.base import DetectionContext, HistoricalStats
from adcopilot.application.detection.rules.rule_01_wasted_search_term import WastedSearchTermRule
from adcopilot.application.detection.rules.rule_02_zero_conversion_keyword import (
    ZeroConversionKeywordRule,
)
from adcopilot.application.detection.rules.rule_03_low_quality_score import (
    LowQualityScoreKeywordRule,
)
from adcopilot.application.detection.rules.rule_04_disapproved_ad import DisapprovedAdRule
from adcopilot.application.detection.rules.rule_05_broad_match_bleeding import (
    BroadMatchBleedingRule,
)
from adcopilot.application.detection.rules.rule_06_no_conversion_tracking import (
    NoConversionTrackingRule,
)
from adcopilot.application.detection.rules.rule_07_budget_capped import BudgetCappedRule
from adcopilot.application.detection.rules.rule_08_single_ad_in_group import SingleAdInGroupRule
from adcopilot.application.detection.rules.rule_09_dead_keyword import DeadKeywordRule
from adcopilot.application.detection.rules.rule_10_wrong_bidding_strategy import (
    WrongBiddingStrategyRule,
)
from adcopilot.application.detection.rules.rule_11_ctr_decline import CtrDeclineRule
from adcopilot.application.detection.rules.rule_12_cpa_spike import CpaSpikeRule
from adcopilot.application.detection.rules.rule_13_conversion_rate_drop import (
    ConversionRateDropRule,
)
from adcopilot.application.detection.rules.rule_14_impression_share_erosion import (
    ImpressionShareErosionRule,
)
from adcopilot.application.detection.rules.rule_15_spend_acceleration import SpendAccelerationRule
from adcopilot.application.detection.rules.rule_16_quality_score_deterioration import (
    QualityScoreDeteriorationRule,
)
from adcopilot.application.detection.rules.rule_17_ad_keyword_mismatch import (
    AdKeywordMismatchRule,
)
from adcopilot.application.detection.rules.rule_18_missing_cta import MissingCtaRule
from adcopilot.application.detection.rules.rule_19_weak_rsa_strength import WeakRsaStrengthRule
from adcopilot.application.detection.rules.rule_20_ad_fatigue import AdFatigueRule
from adcopilot.application.detection.rules.rule_21_redundant_headlines import (
    RedundantHeadlinesRule,
)
from adcopilot.application.detection.rules.rule_22_generic_description import (
    GenericDescriptionRule,
)
from adcopilot.application.detection.rules.rule_23_overstuffed_ad_group import (
    OverstuffedAdGroupRule,
)
from adcopilot.application.detection.rules.rule_24_keyword_cannibalization import (
    KeywordCannibalizationRule,
)
from adcopilot.application.detection.rules.rule_25_negative_keyword_conflict import (
    NegativeKeywordConflictRule,
)
from adcopilot.application.detection.rules.rule_26_orphaned_campaign import OrphanedCampaignRule
from adcopilot.application.detection.rules.rule_27_match_type_redundancy import (
    MatchTypeRedundancyRule,
)
from adcopilot.application.detection.rules.rule_28_device_bid_adjustment import (
    DeviceBidAdjustmentRule,
)
from adcopilot.application.detection.rules.rule_29_geo_exclusion import GeoExclusionRule
from adcopilot.application.detection.rules.rule_30_ad_schedule_adjustment import (
    AdScheduleAdjustmentRule,
)
from adcopilot.application.detection.rules.rule_31_day_of_week_bid_adjustment import (
    DayOfWeekBidAdjustmentRule,
)
from adcopilot.application.detection.rules.rule_32_add_audience_signals import (
    AddAudienceSignalsRule,
)
from adcopilot.application.detection.rules.rule_33_reallocate_budget import ReallocateBudgetRule
from adcopilot.application.detection.rules.rule_34_is_lost_to_budget import IsLostToBudgetRule
from adcopilot.application.detection.rules.rule_35_is_lost_to_rank import IsLostToRankRule
from adcopilot.application.detection.rules.rule_36_relax_target_cpa import RelaxTargetCpaRule
from adcopilot.application.detection.rules.rule_37_diversify_channels import DiversifyChannelsRule
from adcopilot.application.detection.rules.rule_38_upgrade_conversion_action import (
    UpgradeConversionActionRule,
)
from adcopilot.application.detection.rules.rule_39_deduplicate_conversions import (
    DeduplicateConversionsRule,
)
from adcopilot.application.detection.rules.rule_40_set_conversion_value import (
    SetConversionValueRule,
)
from adcopilot.application.detection.rules.rule_41_add_sitelinks import AddSitelinksRule
from adcopilot.application.detection.rules.rule_42_add_callouts import AddCalloutsRule
from adcopilot.application.detection.rules.rule_43_add_structured_snippets import (
    AddStructuredSnippetsRule,
)
from adcopilot.application.detection.rules.rule_44_refresh_sitelink import RefreshSitelinkRule
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.recommendation import RecommendationKind, RecommendationSeverity
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    AudiencePerformanceSnapshot,
    CampaignExtensionSnapshot,
    CampaignSnapshot,
    ConversionActionSnapshot,
    DayOfWeekPerformanceSnapshot,
    DevicePerformanceSnapshot,
    GeoPerformanceSnapshot,
    HourPerformanceSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
    SitelinkPerformanceSnapshot,
    SnapshotId,
)

# ---------------------------------------------------------------------------
# Shared test-data helpers
# ---------------------------------------------------------------------------

_ACCOUNT_ID = AccountId("acct-test-1")
_SNAP_DATE = date(2026, 4, 9)
_NOW = datetime(2026, 4, 9, tzinfo=UTC)


def _account() -> GoogleAdsAccount:
    return GoogleAdsAccount(
        id=_ACCOUNT_ID,
        user_id=UserId("u1"),
        customer_id="123",
        descriptive_name="Test",
        currency="EUR",
        timezone="UTC",
        is_manager=False,
        write_enabled=True,
        connected_at=_NOW,
    )


def _history(
    avg_cpa_micros: int = 10_000_000,
    total_cost: int = 0,
    total_conv: float = 0.0,
) -> HistoricalStats:
    return HistoricalStats(
        avg_cpa_micros=avg_cpa_micros,
        total_cost_micros=total_cost,
        total_conversions=total_conv,
    )


def _ctx(**kwargs) -> DetectionContext:
    defaults = dict(
        account=_account(),
        campaigns=[],
        ad_groups=[],
        keywords=[],
        search_terms=[],
        ads=[],
        history=_history(),
        snapshot_date=_SNAP_DATE,
    )
    defaults.update(kwargs)
    return DetectionContext(**defaults)


def _sid() -> SnapshotId:
    return SnapshotId(str(uuid.uuid4()))


def _campaign(**kwargs) -> CampaignSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=1,
        name="Camp",
        status="ENABLED",
        channel_type="SEARCH",
        budget_micros=10_000_000,
        bidding_strategy="MANUAL_CPC",
        impressions=1000,
        clicks=50,
        cost_micros=5_000_000,
        conversions=1.0,
        conv_value=15.0,
        search_impression_share=None,
        search_budget_lost_impression_share=None,
        search_rank_lost_impression_share=None,
        target_cpa_micros=None,
        all_conversions=0.0,
    )
    defaults.update(kwargs)
    return CampaignSnapshot(**defaults)


def _ad_group(**kwargs) -> AdGroupSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        ad_group_id=10,
        campaign_id=1,
        name="AG",
        status="ENABLED",
        impressions=500,
        clicks=20,
        cost_micros=2_000_000,
        conversions=0.5,
    )
    defaults.update(kwargs)
    return AdGroupSnapshot(**defaults)


def _keyword(**kwargs) -> KeywordSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        criterion_id=100,
        ad_group_id=10,
        text="test keyword",
        match_type="EXACT",
        status="ENABLED",
        quality_score=7,
        impressions=100,
        clicks=5,
        cost_micros=500_000,
        conversions=0.1,
        ctr=0.05,
        avg_cpc_micros=100_000,
    )
    defaults.update(kwargs)
    return KeywordSnapshot(**defaults)


def _search_term(**kwargs) -> SearchTermSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        search_term="test search",
        ad_group_id=10,
        impressions=50,
        clicks=5,
        cost_micros=500_000,
        conversions=0.0,
        matched_keyword_id=100,
    )
    defaults.update(kwargs)
    return SearchTermSnapshot(**defaults)


def _ad(**kwargs) -> AdSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        ad_id=200,
        ad_group_id=10,
        type="EXPANDED_TEXT_AD",
        status="ENABLED",
        headlines_json="[]",
        descriptions_json="[]",
        final_urls_json="[]",
        impressions=100,
        clicks=5,
        cost_micros=500_000,
        conversions=0.1,
    )
    defaults.update(kwargs)
    return AdSnapshot(**defaults)


# ===========================================================================
# Rule 01 - WastedSearchTermRule
# ===========================================================================
#
# Triggers when ALL of:
#   - clicks >= 5
#   - conversions == 0
#   - cost_micros > avg_cpa * 0.3
#   - search_term contains a waste signal (free, jobs, salary, how to, diy,
#     wikipedia, youtube)
# ===========================================================================


class TestRule01WastedSearchTerm:
    rule = WastedSearchTermRule()

    # --- positive ---

    def test_triggers_for_waste_signal_and_high_cost(self):
        # avg_cpa = 10_000_000  →  threshold = 3_000_000
        # cost_micros 5_000_000 > 3_000_000  ✓
        st = _search_term(
            search_term="free trial offer",
            clicks=10,
            cost_micros=5_000_000,
            conversions=0.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ADD_NEGATIVE_KEYWORD
        assert recs[0].evidence["search_term"] == "free trial offer"

    def test_triggers_for_youtube_signal(self):
        st = _search_term(
            search_term="youtube tutorial",
            clicks=20,
            cost_micros=8_000_000,
            conversions=0.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_triggers_for_jobs_signal_case_insensitive(self):
        st = _search_term(
            search_term="JOBS in marketing",
            clicks=7,
            cost_micros=5_000_000,
            conversions=0.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_estimated_savings_equals_cost(self):
        st = _search_term(
            search_term="how to do it",
            clicks=10,
            cost_micros=6_000_000,
            conversions=0.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        recs = self.rule.detect(ctx)
        assert recs[0].estimated_monthly_savings_micros == 6_000_000

    # --- negative ---

    def test_no_trigger_when_conversions_nonzero(self):
        st = _search_term(
            search_term="free trial offer",
            clicks=10,
            cost_micros=5_000_000,
            conversions=1.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_clicks_below_5(self):
        st = _search_term(
            search_term="free trial offer",
            clicks=4,
            cost_micros=5_000_000,
            conversions=0.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_cost_below_threshold(self):
        # threshold = 10_000_000 * 0.3 = 3_000_000; cost = 2_000_000 ≤ threshold
        st = _search_term(
            search_term="free trial offer",
            clicks=10,
            cost_micros=2_000_000,
            conversions=0.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_no_waste_signal_in_term(self):
        st = _search_term(
            search_term="buy premium software",
            clicks=10,
            cost_micros=5_000_000,
            conversions=0.0,
        )
        ctx = _ctx(search_terms=[st], history=_history(avg_cpa_micros=10_000_000))
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_search_terms_returns_empty(self):
        ctx = _ctx(search_terms=[])
        assert self.rule.detect(ctx) == []

    def test_multiple_terms_only_qualifying_flagged(self):
        # One qualifies, one does not (no waste signal)
        st_waste = _search_term(
            search_term="salary negotiation tips",
            clicks=10,
            cost_micros=5_000_000,
            conversions=0.0,
        )
        st_clean = _search_term(
            search_term="buy enterprise plan",
            clicks=10,
            cost_micros=5_000_000,
            conversions=0.0,
        )
        ctx = _ctx(
            search_terms=[st_waste, st_clean],
            history=_history(avg_cpa_micros=10_000_000),
        )
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].evidence["search_term"] == "salary negotiation tips"


# ===========================================================================
# Rule 02 - ZeroConversionKeywordRule
# ===========================================================================
#
# Triggers when ALL of:
#   - avg_cpa_micros != 0
#   - conversions == 0
#   - clicks >= 30
#   - cost_micros >= 2 * avg_cpa
# ===========================================================================


class TestRule02ZeroConversionKeyword:
    rule = ZeroConversionKeywordRule()

    # --- positive ---

    def test_triggers_when_all_conditions_met(self):
        # avg_cpa = 1_000_000  →  threshold = 2_000_000
        kw = _keyword(
            conversions=0.0,
            clicks=30,
            cost_micros=2_000_000,
        )
        ctx = _ctx(keywords=[kw], history=_history(avg_cpa_micros=1_000_000))
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.PAUSE_KEYWORD

    def test_triggers_with_high_click_count(self):
        kw = _keyword(
            conversions=0.0,
            clicks=100,
            cost_micros=5_000_000,
        )
        ctx = _ctx(keywords=[kw], history=_history(avg_cpa_micros=1_000_000))
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_evidence_contains_threshold(self):
        kw = _keyword(conversions=0.0, clicks=50, cost_micros=4_000_000)
        ctx = _ctx(keywords=[kw], history=_history(avg_cpa_micros=1_000_000))
        recs = self.rule.detect(ctx)
        assert recs[0].evidence["threshold_micros"] == 2_000_000

    # --- negative ---

    def test_no_trigger_when_conversions_nonzero(self):
        kw = _keyword(conversions=0.5, clicks=50, cost_micros=4_000_000)
        ctx = _ctx(keywords=[kw], history=_history(avg_cpa_micros=1_000_000))
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_clicks_below_30(self):
        kw = _keyword(conversions=0.0, clicks=29, cost_micros=4_000_000)
        ctx = _ctx(keywords=[kw], history=_history(avg_cpa_micros=1_000_000))
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_cost_below_threshold(self):
        # threshold = 2_000_000; cost = 1_999_999 < threshold
        kw = _keyword(conversions=0.0, clicks=50, cost_micros=1_999_999)
        ctx = _ctx(keywords=[kw], history=_history(avg_cpa_micros=1_000_000))
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_no_trigger_when_avg_cpa_is_zero(self):
        kw = _keyword(conversions=0.0, clicks=50, cost_micros=4_000_000)
        ctx = _ctx(keywords=[kw], history=_history(avg_cpa_micros=0))
        assert self.rule.detect(ctx) == []

    def test_empty_keywords_returns_empty(self):
        ctx = _ctx(keywords=[])
        assert self.rule.detect(ctx) == []

    def test_multiple_keywords_only_qualifying_flagged(self):
        kw_bad = _keyword(criterion_id=1, conversions=0.0, clicks=50, cost_micros=4_000_000)
        kw_ok = _keyword(criterion_id=2, conversions=1.0, clicks=50, cost_micros=4_000_000)
        ctx = _ctx(keywords=[kw_bad, kw_ok], history=_history(avg_cpa_micros=1_000_000))
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].target["criterion_id"] == 1


# ===========================================================================
# Rule 03 - LowQualityScoreKeywordRule
# ===========================================================================
#
# Triggers when ALL of:
#   - quality_score is not None
#   - quality_score <= 4
#   - cost_micros >= 10_000_000
# ===========================================================================


class TestRule03LowQualityScore:
    rule = LowQualityScoreKeywordRule()

    # --- positive ---

    def test_triggers_at_quality_score_4(self):
        kw = _keyword(quality_score=4, cost_micros=10_000_000)
        ctx = _ctx(keywords=[kw])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.PAUSE_KEYWORD
        assert recs[0].severity == RecommendationSeverity.MEDIUM

    def test_triggers_at_quality_score_1(self):
        kw = _keyword(quality_score=1, cost_micros=15_000_000)
        ctx = _ctx(keywords=[kw])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_savings_is_half_of_cost(self):
        kw = _keyword(quality_score=3, cost_micros=20_000_000)
        ctx = _ctx(keywords=[kw])
        recs = self.rule.detect(ctx)
        assert recs[0].estimated_monthly_savings_micros == 10_000_000

    # --- negative ---

    def test_no_trigger_when_quality_score_5(self):
        kw = _keyword(quality_score=5, cost_micros=10_000_000)
        ctx = _ctx(keywords=[kw])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_cost_below_minimum(self):
        kw = _keyword(quality_score=3, cost_micros=9_999_999)
        ctx = _ctx(keywords=[kw])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_quality_score_is_none(self):
        kw = _keyword(quality_score=None, cost_micros=15_000_000)
        ctx = _ctx(keywords=[kw])
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_keywords_returns_empty(self):
        ctx = _ctx(keywords=[])
        assert self.rule.detect(ctx) == []

    def test_multiple_keywords_mixed_scores(self):
        kw_low = _keyword(criterion_id=1, quality_score=2, cost_micros=10_000_000)
        kw_high = _keyword(criterion_id=2, quality_score=8, cost_micros=10_000_000)
        kw_none = _keyword(criterion_id=3, quality_score=None, cost_micros=10_000_000)
        ctx = _ctx(keywords=[kw_low, kw_high, kw_none])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].target["criterion_id"] == 1

    def test_evidence_contains_quality_score(self):
        kw = _keyword(quality_score=2, cost_micros=10_000_000)
        ctx = _ctx(keywords=[kw])
        recs = self.rule.detect(ctx)
        assert recs[0].evidence["quality_score"] == 2


# ===========================================================================
# Rule 04 - DisapprovedAdRule
# ===========================================================================
#
# Triggers for every ad with status == "DISAPPROVED"
# ===========================================================================


class TestRule04DisapprovedAd:
    rule = DisapprovedAdRule()

    # --- positive ---

    def test_triggers_for_disapproved_ad(self):
        ad = _ad(status="DISAPPROVED", ad_id=42)
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.FIX_DISAPPROVED_AD
        assert recs[0].severity == RecommendationSeverity.CRITICAL

    def test_triggers_for_each_disapproved_ad(self):
        ads = [_ad(status="DISAPPROVED", ad_id=i) for i in range(3)]
        ctx = _ctx(ads=ads)
        recs = self.rule.detect(ctx)
        assert len(recs) == 3

    def test_evidence_contains_ad_id_and_status(self):
        ad = _ad(status="DISAPPROVED", ad_id=99)
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert recs[0].evidence["ad_id"] == 99
        assert recs[0].evidence["status"] == "DISAPPROVED"

    # --- negative ---

    def test_no_trigger_for_enabled_ad(self):
        ad = _ad(status="ENABLED")
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_for_paused_ad(self):
        ad = _ad(status="PAUSED")
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_for_removed_ad(self):
        ad = _ad(status="REMOVED")
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_ads_returns_empty(self):
        ctx = _ctx(ads=[])
        assert self.rule.detect(ctx) == []

    def test_mixed_statuses_only_disapproved_flagged(self):
        ad_ok = _ad(status="ENABLED", ad_id=1)
        ad_bad = _ad(status="DISAPPROVED", ad_id=2)
        ctx = _ctx(ads=[ad_ok, ad_bad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].evidence["ad_id"] == 2

    def test_estimated_savings_is_zero(self):
        ad = _ad(status="DISAPPROVED")
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert recs[0].estimated_monthly_savings_micros == 0


# ===========================================================================
# Rule 05 - BroadMatchBleedingRule
# ===========================================================================
#
# Triggers when ALL of:
#   - keyword match_type == "BROAD"
#   - >= 10 search terms matched to that keyword
#   - bleed_ratio (unrelated terms / total terms) >= 0.3
#     where "unrelated" means Jaccard(search_term_tokens, kw_tokens) < 0.5
# ===========================================================================


class TestRule05BroadMatchBleeding:
    rule = BroadMatchBleedingRule()

    def _make_broad_keyword(self, criterion_id: int = 1, text: str = "shoes") -> KeywordSnapshot:
        return _keyword(criterion_id=criterion_id, match_type="BROAD", text=text)

    def _make_unrelated_terms(
        self,
        count: int,
        keyword_id: int = 1,
        ad_group_id: int = 10,
    ) -> list[SearchTermSnapshot]:
        """Terms with no token overlap with keyword 'shoes'."""
        return [
            _search_term(
                search_term=f"car rental deal {i}",
                matched_keyword_id=keyword_id,
                ad_group_id=ad_group_id,
                cost_micros=100_000,
            )
            for i in range(count)
        ]

    def _make_related_terms(
        self,
        count: int,
        keyword_id: int = 1,
        ad_group_id: int = 10,
    ) -> list[SearchTermSnapshot]:
        """Terms with Jaccard >= 0.5 relative to keyword 'shoes'.

        'running shoes' → tokens {'running','shoes'}: intersection={'shoes'}=1,
        union=2, Jaccard=0.5 which is NOT < 0.5 (the threshold), so these
        terms are NOT classified as unrelated by the rule.
        """
        return [
            _search_term(
                search_term="running shoes",
                matched_keyword_id=keyword_id,
                ad_group_id=ad_group_id,
            )
            for _ in range(count)
        ]

    # --- positive ---

    def test_triggers_when_bleed_ratio_above_threshold(self):
        kw = self._make_broad_keyword()
        # 10 unrelated + 0 related = 100% bleed (> 0.3)
        terms = self._make_unrelated_terms(10)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.CHANGE_MATCH_TYPE

    def test_suggested_match_type_is_phrase(self):
        kw = self._make_broad_keyword()
        terms = self._make_unrelated_terms(10)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        recs = self.rule.detect(ctx)
        assert recs[0].payload["suggested_match_type"] == "PHRASE"

    def test_triggers_with_bleed_just_at_threshold(self):
        kw = self._make_broad_keyword()
        # 4 unrelated + 6 related → bleed = 4/10 = 0.4 ≥ 0.3
        terms = self._make_unrelated_terms(4) + self._make_related_terms(6)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    # --- negative ---

    def test_no_trigger_for_exact_match_keyword(self):
        kw = _keyword(criterion_id=1, match_type="EXACT", text="shoes")
        terms = self._make_unrelated_terms(10)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        assert self.rule.detect(ctx) == []

    def test_no_trigger_for_phrase_match_keyword(self):
        kw = _keyword(criterion_id=1, match_type="PHRASE", text="shoes")
        terms = self._make_unrelated_terms(10)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_fewer_than_10_triggered_terms(self):
        kw = self._make_broad_keyword()
        terms = self._make_unrelated_terms(9)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_bleed_ratio_below_threshold(self):
        kw = self._make_broad_keyword()
        # 2 unrelated + 8 related → bleed = 2/10 = 0.2 < 0.3
        terms = self._make_unrelated_terms(2) + self._make_related_terms(8)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_context_returns_empty(self):
        ctx = _ctx()
        assert self.rule.detect(ctx) == []

    def test_broad_keyword_with_no_matching_terms_skipped(self):
        # Rule now groups by ad_group_id. Put the keyword in ad_group 99
        # and all search terms in ad_group 999 (different) — no match.
        kw = _keyword(criterion_id=1, match_type="BROAD", text="shoes", ad_group_id=99)
        terms = self._make_unrelated_terms(10, ad_group_id=999)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        assert self.rule.detect(ctx) == []

    def test_bleed_ratio_recorded_in_evidence(self):
        kw = self._make_broad_keyword()
        terms = self._make_unrelated_terms(10)
        ctx = _ctx(keywords=[kw], search_terms=terms)
        recs = self.rule.detect(ctx)
        assert "bleed_ratio" in recs[0].evidence
        assert recs[0].evidence["bleed_ratio"] == 1.0


# ===========================================================================
# Rule 06 - NoConversionTrackingRule
# ===========================================================================
#
# Triggers when ALL of:
#   - sum(campaign.cost_micros) >= 100_000_000
#   - sum(campaign.conversions) == 0
# ===========================================================================


class TestRule06NoConversionTracking:
    rule = NoConversionTrackingRule()

    # --- positive ---

    def test_triggers_when_high_spend_and_zero_conversions(self):
        c = _campaign(cost_micros=100_000_000, conversions=0.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ENABLE_CONVERSION_TRACKING
        assert recs[0].severity == RecommendationSeverity.CRITICAL

    def test_triggers_with_multiple_campaigns_no_conversions(self):
        c1 = _campaign(campaign_id=1, cost_micros=60_000_000, conversions=0.0)
        c2 = _campaign(campaign_id=2, cost_micros=60_000_000, conversions=0.0)
        ctx = _ctx(campaigns=[c1, c2])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_evidence_contains_totals(self):
        c = _campaign(cost_micros=150_000_000, conversions=0.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert recs[0].evidence["total_cost_micros"] == 150_000_000
        assert recs[0].evidence["total_conversions"] == 0

    # --- negative ---

    def test_no_trigger_when_conversions_exist(self):
        c = _campaign(cost_micros=200_000_000, conversions=5.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_cost_below_minimum(self):
        c = _campaign(cost_micros=99_999_999, conversions=0.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_any_campaign_has_conversions(self):
        c1 = _campaign(campaign_id=1, cost_micros=100_000_000, conversions=0.0)
        c2 = _campaign(campaign_id=2, cost_micros=100_000_000, conversions=1.0)
        ctx = _ctx(campaigns=[c1, c2])
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_campaigns_returns_empty(self):
        ctx = _ctx(campaigns=[])
        assert self.rule.detect(ctx) == []

    def test_exactly_at_minimum_cost_triggers(self):
        c = _campaign(cost_micros=100_000_000, conversions=0.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1


# ===========================================================================
# Rule 07 - BudgetCappedRule
# ===========================================================================
#
# Triggers when ALL of:
#   - budget_micros > 0
#   - (cost_micros / 30) >= budget_micros * 0.95  (cap proxy)
#   - conv_value > 0 and cost_micros > 0
#   - ROAS = (conv_value * 1_000_000) / cost_micros > 1.0
# ===========================================================================


class TestRule07BudgetCapped:
    rule = BudgetCappedRule()

    # --- positive ---

    def test_triggers_when_capped_and_positive_roas(self):
        # budget = 1_000_000; daily_avg = 30_000_000 / 30 = 1_000_000
        # 1_000_000 >= 1_000_000 * 0.95 → True
        # roas = (50.0 * 1_000_000) / 30_000_000 ≈ 1.67 > 1.0 → True
        c = _campaign(
            budget_micros=1_000_000,
            cost_micros=30_000_000,
            conv_value=50.0,
            conversions=5.0,
        )
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.INCREASE_BUDGET

    def test_suggested_budget_is_20_percent_increase(self):
        c = _campaign(
            budget_micros=1_000_000,
            cost_micros=30_000_000,
            conv_value=50.0,
        )
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert recs[0].payload["suggested_budget_micros"] == 1_200_000

    def test_roas_recorded_in_evidence(self):
        c = _campaign(
            budget_micros=1_000_000,
            cost_micros=30_000_000,
            conv_value=50.0,
        )
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert recs[0].evidence["roas"] > 1.0

    # --- negative ---

    def test_no_trigger_when_roas_below_1(self):
        # roas = (0.01 * 1_000_000) / 30_000_000 ≈ 0.00033 < 1.0
        c = _campaign(
            budget_micros=1_000_000,
            cost_micros=30_000_000,
            conv_value=0.01,
        )
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_not_at_cap(self):
        # budget = 10_000_000; daily_avg = 1_000_000 / 30 ≈ 33_333
        # 33_333 < 10_000_000 * 0.95 → not capped
        c = _campaign(
            budget_micros=10_000_000,
            cost_micros=1_000_000,
            conv_value=50.0,
        )
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_budget_is_zero(self):
        c = _campaign(
            budget_micros=0,
            cost_micros=30_000_000,
            conv_value=50.0,
        )
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_conv_value_is_zero(self):
        c = _campaign(
            budget_micros=1_000_000,
            cost_micros=30_000_000,
            conv_value=0.0,
        )
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_campaigns_returns_empty(self):
        ctx = _ctx(campaigns=[])
        assert self.rule.detect(ctx) == []

    def test_multiple_campaigns_only_capped_positive_roas_flagged(self):
        c_capped = _campaign(
            campaign_id=1,
            budget_micros=1_000_000,
            cost_micros=30_000_000,
            conv_value=50.0,
        )
        c_not_capped = _campaign(
            campaign_id=2,
            budget_micros=50_000_000,
            cost_micros=10_000_000,
            conv_value=50.0,
        )
        ctx = _ctx(campaigns=[c_capped, c_not_capped])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].target["campaign_id"] == 1


# ===========================================================================
# Rule 08 - SingleAdInGroupRule
# ===========================================================================
#
# Triggers when ALL of:
#   - ad_group has exactly 1 non-REMOVED active ad
#   - ad_group object exists and has impressions >= 100
# ===========================================================================


class TestRule08SingleAdInGroup:
    rule = SingleAdInGroupRule()

    # --- positive ---

    def test_triggers_for_single_enabled_ad_with_enough_impressions(self):
        ag = _ad_group(ad_group_id=10, impressions=200)
        ad = _ad(ad_group_id=10, status="ENABLED")
        ctx = _ctx(ad_groups=[ag], ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ADD_AD_VARIATION
        assert recs[0].severity == RecommendationSeverity.LOW

    def test_triggers_single_paused_ad_still_counted_as_active(self):
        # PAUSED is not REMOVED, so it is active
        ag = _ad_group(ad_group_id=10, impressions=200)
        ad = _ad(ad_group_id=10, status="PAUSED")
        ctx = _ctx(ad_groups=[ag], ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_evidence_contains_ad_group_name_and_impressions(self):
        ag = _ad_group(ad_group_id=10, name="My Group", impressions=500)
        ad = _ad(ad_group_id=10, status="ENABLED")
        ctx = _ctx(ad_groups=[ag], ads=[ad])
        recs = self.rule.detect(ctx)
        assert recs[0].evidence["ad_group_name"] == "My Group"
        assert recs[0].evidence["impressions"] == 500

    # --- negative ---

    def test_no_trigger_when_two_active_ads(self):
        ag = _ad_group(ad_group_id=10, impressions=200)
        ads = [_ad(ad_id=i, ad_group_id=10, status="ENABLED") for i in range(2)]
        ctx = _ctx(ad_groups=[ag], ads=ads)
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        ag = _ad_group(ad_group_id=10, impressions=99)
        ad = _ad(ad_group_id=10, status="ENABLED")
        ctx = _ctx(ad_groups=[ag], ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_removed_ads_not_counted(self):
        # Two ads in group but both REMOVED → no active ads → does not trigger
        ag = _ad_group(ad_group_id=10, impressions=200)
        ads = [_ad(ad_id=i, ad_group_id=10, status="REMOVED") for i in range(2)]
        ctx = _ctx(ad_groups=[ag], ads=ads)
        assert self.rule.detect(ctx) == []

    def test_one_removed_one_active_gives_single_active(self):
        ag = _ad_group(ad_group_id=10, impressions=200)
        ad_rem = _ad(ad_id=1, ad_group_id=10, status="REMOVED")
        ad_ena = _ad(ad_id=2, ad_group_id=10, status="ENABLED")
        ctx = _ctx(ad_groups=[ag], ads=[ad_rem, ad_ena])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    # --- edge ---

    def test_empty_context_returns_empty(self):
        ctx = _ctx()
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_ad_group_object_missing(self):
        # Ad exists but no matching AdGroupSnapshot → no_trigger
        ad = _ad(ad_group_id=99, status="ENABLED")
        ctx = _ctx(ad_groups=[], ads=[ad])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 09 - DeadKeywordRule
# ===========================================================================
#
# Triggers when ALL of:
#   - impressions == 0
#   - status == "ENABLED"
# ===========================================================================


class TestRule09DeadKeyword:
    rule = DeadKeywordRule()

    # --- positive ---

    def test_triggers_for_enabled_keyword_with_zero_impressions(self):
        kw = _keyword(impressions=0, status="ENABLED")
        ctx = _ctx(keywords=[kw])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.PAUSE_KEYWORD
        assert recs[0].severity == RecommendationSeverity.LOW

    def test_triggers_for_multiple_dead_keywords(self):
        kws = [_keyword(criterion_id=i, impressions=0, status="ENABLED") for i in range(3)]
        ctx = _ctx(keywords=kws)
        recs = self.rule.detect(ctx)
        assert len(recs) == 3

    def test_evidence_contains_keyword_text_and_days_checked(self):
        kw = _keyword(text="dead word", impressions=0, status="ENABLED")
        ctx = _ctx(keywords=[kw])
        recs = self.rule.detect(ctx)
        assert recs[0].evidence["keyword_text"] == "dead word"
        assert recs[0].evidence["days_checked"] == 30

    # --- negative ---

    def test_no_trigger_when_impressions_nonzero(self):
        kw = _keyword(impressions=1, status="ENABLED")
        ctx = _ctx(keywords=[kw])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_paused_keyword_with_zero_impressions(self):
        kw = _keyword(impressions=0, status="PAUSED")
        ctx = _ctx(keywords=[kw])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_removed_keyword_with_zero_impressions(self):
        kw = _keyword(impressions=0, status="REMOVED")
        ctx = _ctx(keywords=[kw])
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_keywords_returns_empty(self):
        ctx = _ctx(keywords=[])
        assert self.rule.detect(ctx) == []

    def test_mixed_keywords_only_dead_enabled_flagged(self):
        kw_dead = _keyword(criterion_id=1, impressions=0, status="ENABLED")
        kw_live = _keyword(criterion_id=2, impressions=100, status="ENABLED")
        kw_paused_dead = _keyword(criterion_id=3, impressions=0, status="PAUSED")
        ctx = _ctx(keywords=[kw_dead, kw_live, kw_paused_dead])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].target["criterion_id"] == 1

    def test_estimated_savings_is_zero(self):
        kw = _keyword(impressions=0, status="ENABLED")
        ctx = _ctx(keywords=[kw])
        recs = self.rule.detect(ctx)
        assert recs[0].estimated_monthly_savings_micros == 0


# ===========================================================================
# Rule 10 - WrongBiddingStrategyRule
# ===========================================================================
#
# Triggers when ALL of:
#   - campaign.bidding_strategy contains "MAXIMIZE_CLICKS" (case-insensitive)
#   - campaign.conversions >= 30
# ===========================================================================


class TestRule10WrongBiddingStrategy:
    rule = WrongBiddingStrategyRule()

    # --- positive ---

    def test_triggers_for_maximize_clicks_with_enough_conversions(self):
        c = _campaign(bidding_strategy="MAXIMIZE_CLICKS", conversions=30.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ADJUST_BIDDING_STRATEGY

    def test_suggested_strategy_is_maximize_conversions(self):
        c = _campaign(bidding_strategy="MAXIMIZE_CLICKS", conversions=50.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert recs[0].payload["suggested_strategy"] == "MAXIMIZE_CONVERSIONS"

    def test_current_strategy_recorded_in_payload(self):
        c = _campaign(bidding_strategy="MAXIMIZE_CLICKS", conversions=50.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert recs[0].payload["current_strategy"] == "MAXIMIZE_CLICKS"

    def test_triggers_case_insensitive_strategy(self):
        c = _campaign(bidding_strategy="maximize_clicks", conversions=50.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    # --- negative ---

    def test_no_trigger_for_manual_cpc(self):
        c = _campaign(bidding_strategy="MANUAL_CPC", conversions=50.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_for_maximize_conversions_already(self):
        c = _campaign(bidding_strategy="MAXIMIZE_CONVERSIONS", conversions=50.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_conversions_below_minimum(self):
        c = _campaign(bidding_strategy="MAXIMIZE_CLICKS", conversions=29.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    # --- edge ---

    def test_empty_campaigns_returns_empty(self):
        ctx = _ctx(campaigns=[])
        assert self.rule.detect(ctx) == []

    def test_exactly_at_minimum_conversions_triggers(self):
        c = _campaign(bidding_strategy="MAXIMIZE_CLICKS", conversions=30.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_multiple_campaigns_only_qualifying_flagged(self):
        c_bad = _campaign(campaign_id=1, bidding_strategy="MAXIMIZE_CLICKS", conversions=50.0)
        c_ok = _campaign(campaign_id=2, bidding_strategy="TARGET_CPA", conversions=50.0)
        c_few = _campaign(campaign_id=3, bidding_strategy="MAXIMIZE_CLICKS", conversions=5.0)
        ctx = _ctx(campaigns=[c_bad, c_ok, c_few])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].target["campaign_id"] == 1


# ===========================================================================
# Rule 23 - OverstuffedAdGroupRule
# ===========================================================================


def _neg_kw(**kwargs) -> NegativeKeywordSnapshot:
    defaults = dict(
        id=SnapshotId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        criterion_id=999,
        campaign_id=1,
        ad_group_id=0,
        text="free",
        match_type="BROAD",
    )
    defaults.update(kwargs)
    return NegativeKeywordSnapshot(**defaults)


class TestOverstuffedAdGroupRule:
    rule = OverstuffedAdGroupRule()

    def test_ad_group_with_16_enabled_keywords_triggers(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        keywords = [
            _keyword(criterion_id=i, ad_group_id=10, status="ENABLED")
            for i in range(16)
        ]
        ctx = _ctx(ad_groups=[ag], keywords=keywords)
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.OVERSTUFFED_AD_GROUP
        assert recs[0].evidence["enabled_keywords"] == 16

    def test_ad_group_with_15_keywords_not_triggered(self):
        ag = _ad_group(ad_group_id=10)
        keywords = [
            _keyword(criterion_id=i, ad_group_id=10, status="ENABLED")
            for i in range(15)
        ]
        ctx = _ctx(ad_groups=[ag], keywords=keywords)
        assert self.rule.detect(ctx) == []

    def test_paused_keywords_not_counted(self):
        ag = _ad_group(ad_group_id=10)
        # 10 enabled + 10 paused = only 10 enabled → should NOT trigger
        kws = [_keyword(criterion_id=i, ad_group_id=10, status="ENABLED") for i in range(10)]
        kws += [_keyword(criterion_id=i + 100, ad_group_id=10, status="PAUSED") for i in range(10)]
        ctx = _ctx(ad_groups=[ag], keywords=kws)
        assert self.rule.detect(ctx) == []

    def test_multiple_ad_groups_only_overstuffed_flagged(self):
        ag1 = _ad_group(ad_group_id=10, campaign_id=1)
        ag2 = _ad_group(ad_group_id=20, campaign_id=1)
        kws_ag1 = [_keyword(criterion_id=i, ad_group_id=10, status="ENABLED") for i in range(20)]
        kws_ag2 = [_keyword(criterion_id=i + 100, ad_group_id=20, status="ENABLED") for i in range(5)]
        ctx = _ctx(ad_groups=[ag1, ag2], keywords=kws_ag1 + kws_ag2)
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].target["ad_group_id"] == 10


# ===========================================================================
# Rule 24 - KeywordCannibalizationRule
# ===========================================================================


class TestKeywordCannibalizationRule:
    rule = KeywordCannibalizationRule()

    def test_same_keyword_in_two_ad_groups_triggers(self):
        ag1 = _ad_group(ad_group_id=10, campaign_id=1)
        ag2 = _ad_group(ad_group_id=20, campaign_id=1)
        kw1 = _keyword(criterion_id=1, ad_group_id=10, text="buy shoes", status="ENABLED")
        kw2 = _keyword(criterion_id=2, ad_group_id=20, text="buy shoes", status="ENABLED")
        ctx = _ctx(ad_groups=[ag1, ag2], keywords=[kw1, kw2])
        recs = self.rule.detect(ctx)
        # One rec per ad group for the duplicated keyword
        assert len(recs) == 2
        assert all(r.kind == RecommendationKind.KEYWORD_CANNIBALIZATION for r in recs)
        ad_group_ids = {r.target["ad_group_id"] for r in recs}
        assert ad_group_ids == {10, 20}

    def test_unique_keywords_not_triggered(self):
        ag = _ad_group(ad_group_id=10)
        kw1 = _keyword(criterion_id=1, ad_group_id=10, text="buy shoes", status="ENABLED")
        kw2 = _keyword(criterion_id=2, ad_group_id=10, text="buy boots", status="ENABLED")
        ctx = _ctx(ad_groups=[ag], keywords=[kw1, kw2])
        assert self.rule.detect(ctx) == []

    def test_removed_keywords_ignored(self):
        ag1 = _ad_group(ad_group_id=10)
        ag2 = _ad_group(ad_group_id=20)
        kw1 = _keyword(criterion_id=1, ad_group_id=10, text="buy shoes", status="ENABLED")
        kw2 = _keyword(criterion_id=2, ad_group_id=20, text="buy shoes", status="REMOVED")
        ctx = _ctx(ad_groups=[ag1, ag2], keywords=[kw1, kw2])
        # Only one enabled → no cannibalization
        assert self.rule.detect(ctx) == []

    def test_normalised_text_case_insensitive(self):
        ag1 = _ad_group(ad_group_id=10)
        ag2 = _ad_group(ad_group_id=20)
        kw1 = _keyword(criterion_id=1, ad_group_id=10, text="Buy Shoes", status="ENABLED")
        kw2 = _keyword(criterion_id=2, ad_group_id=20, text="buy shoes", status="ENABLED")
        ctx = _ctx(ad_groups=[ag1, ag2], keywords=[kw1, kw2])
        recs = self.rule.detect(ctx)
        assert len(recs) == 2


# ===========================================================================
# Rule 25 - NegativeKeywordConflictRule
# ===========================================================================


class TestNegativeKeywordConflictRule:
    rule = NegativeKeywordConflictRule()

    def test_exact_campaign_level_conflict_triggers(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="EXACT")
        neg = _neg_kw(campaign_id=1, ad_group_id=0, text="running shoes", match_type="EXACT")
        ctx = _ctx(ad_groups=[ag], keywords=[kw], negative_keywords=[neg])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.NEGATIVE_KEYWORD_CONFLICT
        assert recs[0].evidence["conflict_scope"] == "CAMPAIGN"

    def test_phrase_match_conflict_triggers(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw = _keyword(criterion_id=1, ad_group_id=10, text="buy running shoes online")
        neg = _neg_kw(campaign_id=1, ad_group_id=0, text="running shoes", match_type="PHRASE")
        ctx = _ctx(ad_groups=[ag], keywords=[kw], negative_keywords=[neg])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_broad_match_conflict_triggers(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw = _keyword(criterion_id=1, ad_group_id=10, text="cheap running shoes")
        neg = _neg_kw(campaign_id=1, ad_group_id=0, text="shoes", match_type="BROAD")
        ctx = _ctx(ad_groups=[ag], keywords=[kw], negative_keywords=[neg])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_no_conflict_when_different_campaign(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw = _keyword(criterion_id=1, ad_group_id=10, text="running shoes")
        # Negative is in campaign_id=2, not 1
        neg = _neg_kw(campaign_id=2, ad_group_id=0, text="running shoes", match_type="EXACT")
        ctx = _ctx(ad_groups=[ag], keywords=[kw], negative_keywords=[neg])
        assert self.rule.detect(ctx) == []

    def test_no_negative_keywords_returns_empty(self):
        kw = _keyword(criterion_id=1, ad_group_id=10, text="running shoes")
        ctx = _ctx(keywords=[kw], negative_keywords=[])
        assert self.rule.detect(ctx) == []

    def test_paused_keyword_not_checked(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", status="PAUSED")
        neg = _neg_kw(campaign_id=1, ad_group_id=0, text="running shoes", match_type="EXACT")
        ctx = _ctx(ad_groups=[ag], keywords=[kw], negative_keywords=[neg])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 26 - OrphanedCampaignRule
# ===========================================================================


class TestOrphanedCampaignRule:
    rule = OrphanedCampaignRule()

    def test_enabled_campaign_with_no_ad_groups_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", budget_micros=10_000_000)
        ctx = _ctx(campaigns=[c], ad_groups=[])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ORPHANED_CAMPAIGN
        assert recs[0].estimated_monthly_savings_micros == 10_000_000 * 30

    def test_campaign_with_all_paused_ad_groups_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", budget_micros=5_000_000)
        ag1 = _ad_group(ad_group_id=10, campaign_id=1, status="PAUSED")
        ag2 = _ad_group(ad_group_id=20, campaign_id=1, status="REMOVED")
        ctx = _ctx(campaigns=[c], ad_groups=[ag1, ag2])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_campaign_with_enabled_ad_group_not_triggered(self):
        c = _campaign(campaign_id=1, status="ENABLED", budget_micros=5_000_000)
        ag = _ad_group(ad_group_id=10, campaign_id=1, status="ENABLED")
        ctx = _ctx(campaigns=[c], ad_groups=[ag])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_not_checked(self):
        c = _campaign(campaign_id=1, status="PAUSED", budget_micros=5_000_000)
        ctx = _ctx(campaigns=[c], ad_groups=[])
        assert self.rule.detect(ctx) == []

    def test_zero_budget_campaign_not_triggered(self):
        c = _campaign(campaign_id=1, status="ENABLED", budget_micros=0)
        ctx = _ctx(campaigns=[c], ad_groups=[])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 27 - MatchTypeRedundancyRule
# ===========================================================================


class TestMatchTypeRedundancyRule:
    rule = MatchTypeRedundancyRule()

    def test_broad_and_exact_same_ad_group_triggers(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw_broad = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="BROAD")
        kw_exact = _keyword(criterion_id=2, ad_group_id=10, text="running shoes", match_type="EXACT")
        ctx = _ctx(ad_groups=[ag], keywords=[kw_broad, kw_exact])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.MATCH_TYPE_REDUNDANCY
        assert recs[0].evidence["redundant_match_type"] == "BROAD"

    def test_broad_and_phrase_same_ad_group_triggers(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw_broad = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="BROAD")
        kw_phrase = _keyword(criterion_id=2, ad_group_id=10, text="running shoes", match_type="PHRASE")
        ctx = _ctx(ad_groups=[ag], keywords=[kw_broad, kw_phrase])
        assert len(self.rule.detect(ctx)) == 1

    def test_exact_only_not_triggered(self):
        ag = _ad_group(ad_group_id=10)
        kw = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="EXACT")
        ctx = _ctx(ad_groups=[ag], keywords=[kw])
        assert self.rule.detect(ctx) == []

    def test_broad_only_not_triggered(self):
        ag = _ad_group(ad_group_id=10)
        kw = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="BROAD")
        ctx = _ctx(ad_groups=[ag], keywords=[kw])
        assert self.rule.detect(ctx) == []

    def test_same_text_different_ad_groups_not_triggered(self):
        ag1 = _ad_group(ad_group_id=10, campaign_id=1)
        ag2 = _ad_group(ad_group_id=20, campaign_id=1)
        kw_broad = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="BROAD")
        kw_exact = _keyword(criterion_id=2, ad_group_id=20, text="running shoes", match_type="EXACT")
        ctx = _ctx(ad_groups=[ag1, ag2], keywords=[kw_broad, kw_exact])
        assert self.rule.detect(ctx) == []

    def test_paused_keywords_ignored(self):
        ag = _ad_group(ad_group_id=10, campaign_id=1)
        kw_broad = _keyword(criterion_id=1, ad_group_id=10, text="running shoes", match_type="BROAD", status="PAUSED")
        kw_exact = _keyword(criterion_id=2, ad_group_id=10, text="running shoes", match_type="EXACT", status="ENABLED")
        ctx = _ctx(ad_groups=[ag], keywords=[kw_broad, kw_exact])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Module 4 helpers
# ===========================================================================


def _device_perf(**kwargs) -> DevicePerformanceSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=1,
        device="DESKTOP",
        impressions=500,
        clicks=30,
        cost_micros=10_000_000,
        conversions=10.0,
    )
    defaults.update(kwargs)
    return DevicePerformanceSnapshot(**defaults)


def _geo_perf(**kwargs) -> GeoPerformanceSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=1,
        location_id=1012695,  # example geo criterion ID
        impressions=200,
        clicks=25,
        cost_micros=60_000_000,
        conversions=0.0,
    )
    defaults.update(kwargs)
    return GeoPerformanceSnapshot(**defaults)


def _hour_perf(**kwargs) -> HourPerformanceSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=1,
        hour_of_day=3,
        impressions=50,
        clicks=10,
        cost_micros=25_000_000,
        conversions=0.0,
    )
    defaults.update(kwargs)
    return HourPerformanceSnapshot(**defaults)


def _dow_perf(**kwargs) -> DayOfWeekPerformanceSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=1,
        day_of_week="SUNDAY",
        impressions=300,
        clicks=20,
        cost_micros=30_000_000,
        conversions=1.0,
    )
    defaults.update(kwargs)
    return DayOfWeekPerformanceSnapshot(**defaults)


def _audience_perf(**kwargs) -> AudiencePerformanceSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=1,
        ad_group_id=10,
        criterion_id=555,
        impressions=100,
        clicks=5,
        cost_micros=2_000_000,
        conversions=0.5,
    )
    defaults.update(kwargs)
    return AudiencePerformanceSnapshot(**defaults)


# ===========================================================================
# Rule 28 - DeviceBidAdjustmentRule
# ===========================================================================


class TestDeviceBidAdjustmentRule:
    rule = DeviceBidAdjustmentRule()

    def test_mobile_cpa_2x_desktop_triggers(self):
        # Desktop: 10M cost, 50 conversions → CPA = 200k
        # Mobile: 20M cost, 5 conversions → CPA = 4M (20× desktop)
        desktop = _device_perf(device="DESKTOP", cost_micros=10_000_000, conversions=50.0)
        mobile = _device_perf(device="MOBILE", cost_micros=20_000_000, conversions=5.0)
        ctx = _ctx(device_performance=[desktop, mobile])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.DEVICE_BID_ADJUSTMENT
        assert recs[0].severity == RecommendationSeverity.HIGH
        assert recs[0].evidence["ratio"] > 2.0

    def test_equal_cpa_no_trigger(self):
        desktop = _device_perf(device="DESKTOP", cost_micros=10_000_000, conversions=50.0)
        mobile = _device_perf(device="MOBILE", cost_micros=10_000_000, conversions=50.0)
        ctx = _ctx(device_performance=[desktop, mobile])
        assert self.rule.detect(ctx) == []

    def test_insufficient_desktop_conversions_no_trigger(self):
        # Desktop only 10 conversions — below threshold of 30
        desktop = _device_perf(device="DESKTOP", cost_micros=5_000_000, conversions=10.0)
        mobile = _device_perf(device="MOBILE", cost_micros=20_000_000, conversions=2.0)
        ctx = _ctx(device_performance=[desktop, mobile])
        assert self.rule.detect(ctx) == []

    def test_no_mobile_data_no_trigger(self):
        desktop = _device_perf(device="DESKTOP", cost_micros=10_000_000, conversions=50.0)
        ctx = _ctx(device_performance=[desktop])
        assert self.rule.detect(ctx) == []

    def test_empty_data_no_trigger(self):
        ctx = _ctx(device_performance=[])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 29 - GeoExclusionRule
# ===========================================================================


class TestGeoExclusionRule:
    rule = GeoExclusionRule()

    def test_high_spend_zero_conv_triggers(self):
        geo = _geo_perf(cost_micros=60_000_000, clicks=25, conversions=0.0)
        ctx = _ctx(geo_performance=[geo])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.GEO_EXCLUSION
        assert recs[0].severity == RecommendationSeverity.HIGH

    def test_location_with_conversions_not_triggered(self):
        geo = _geo_perf(cost_micros=60_000_000, clicks=25, conversions=1.0)
        ctx = _ctx(geo_performance=[geo])
        assert self.rule.detect(ctx) == []

    def test_low_spend_not_triggered(self):
        geo = _geo_perf(cost_micros=10_000_000, clicks=25, conversions=0.0)
        ctx = _ctx(geo_performance=[geo])
        assert self.rule.detect(ctx) == []

    def test_low_clicks_not_triggered(self):
        geo = _geo_perf(cost_micros=60_000_000, clicks=5, conversions=0.0)
        ctx = _ctx(geo_performance=[geo])
        assert self.rule.detect(ctx) == []

    def test_empty_data_no_trigger(self):
        ctx = _ctx(geo_performance=[])
        assert self.rule.detect(ctx) == []

    def test_multiple_bad_geos_multiple_recs(self):
        geo1 = _geo_perf(location_id=111, cost_micros=60_000_000, clicks=30, conversions=0.0)
        geo2 = _geo_perf(location_id=222, cost_micros=80_000_000, clicks=40, conversions=0.0)
        ctx = _ctx(geo_performance=[geo1, geo2])
        assert len(self.rule.detect(ctx)) == 2


# ===========================================================================
# Rule 30 - AdScheduleAdjustmentRule
# ===========================================================================


class TestAdScheduleAdjustmentRule:
    rule = AdScheduleAdjustmentRule()

    def test_high_spend_zero_conv_hour_triggers(self):
        h = _hour_perf(hour_of_day=2, cost_micros=25_000_000, conversions=0.0)
        ctx = _ctx(hour_performance=[h])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.AD_SCHEDULE_ADJUSTMENT
        assert recs[0].severity == RecommendationSeverity.MEDIUM
        assert recs[0].evidence["hour_of_day"] == 2

    def test_hour_with_conversions_not_triggered(self):
        h = _hour_perf(hour_of_day=2, cost_micros=25_000_000, conversions=1.0)
        ctx = _ctx(hour_performance=[h])
        assert self.rule.detect(ctx) == []

    def test_low_spend_not_triggered(self):
        h = _hour_perf(hour_of_day=2, cost_micros=5_000_000, conversions=0.0)
        ctx = _ctx(hour_performance=[h])
        assert self.rule.detect(ctx) == []

    def test_empty_data_no_trigger(self):
        ctx = _ctx(hour_performance=[])
        assert self.rule.detect(ctx) == []

    def test_aggregation_across_days(self):
        # Two rows for same campaign+hour on different days — should aggregate
        h1 = _hour_perf(snapshot_date=date(2026, 4, 1), hour_of_day=3, cost_micros=12_000_000, conversions=0.0)
        h2 = _hour_perf(snapshot_date=date(2026, 4, 2), hour_of_day=3, cost_micros=12_000_000, conversions=0.0)
        ctx = _ctx(hour_performance=[h1, h2])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].evidence["cost_micros"] == 24_000_000


# ===========================================================================
# Rule 31 - DayOfWeekBidAdjustmentRule
# ===========================================================================


class TestDayOfWeekBidAdjustmentRule:
    rule = DayOfWeekBidAdjustmentRule()

    def test_sunday_cpa_above_threshold_triggers(self):
        # Account avg CPA = 1_000_000 micros; Sunday CPA = 2_000_000 (2× > 1.5×)
        # Sunday: 30M cost, 15 conversions → CPA = 2M
        dow = _dow_perf(day_of_week="SUNDAY", cost_micros=30_000_000, conversions=15.0)
        ctx = _ctx(
            day_of_week_performance=[dow],
            history=_history(avg_cpa_micros=1_000_000, total_conv=100.0),
        )
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.DAY_OF_WEEK_BID_ADJUSTMENT
        assert recs[0].severity == RecommendationSeverity.MEDIUM
        assert recs[0].evidence["day_of_week"] == "SUNDAY"

    def test_day_below_threshold_not_triggered(self):
        # Account avg CPA = 1M; Monday CPA = 1.2M (< 1.5× threshold)
        dow = _dow_perf(day_of_week="MONDAY", cost_micros=12_000_000, conversions=10.0)
        ctx = _ctx(
            day_of_week_performance=[dow],
            history=_history(avg_cpa_micros=1_000_000, total_conv=100.0),
        )
        assert self.rule.detect(ctx) == []

    def test_insufficient_conversions_not_triggered(self):
        # CPA is bad but only 5 conversions (< 10 threshold)
        dow = _dow_perf(day_of_week="SUNDAY", cost_micros=15_000_000, conversions=5.0)
        ctx = _ctx(
            day_of_week_performance=[dow],
            history=_history(avg_cpa_micros=1_000_000, total_conv=100.0),
        )
        assert self.rule.detect(ctx) == []

    def test_no_account_conversions_no_trigger(self):
        dow = _dow_perf(day_of_week="SUNDAY", cost_micros=30_000_000, conversions=15.0)
        ctx = _ctx(
            day_of_week_performance=[dow],
            history=_history(avg_cpa_micros=0, total_conv=0.0),
        )
        assert self.rule.detect(ctx) == []

    def test_empty_data_no_trigger(self):
        ctx = _ctx(
            day_of_week_performance=[],
            history=_history(avg_cpa_micros=1_000_000, total_conv=100.0),
        )
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 32 - AddAudienceSignalsRule
# ===========================================================================


class TestAddAudienceSignalsRule:
    rule = AddAudienceSignalsRule()

    def test_search_campaign_no_audiences_high_impressions_triggers(self):
        c = _campaign(campaign_id=1, channel_type="SEARCH", status="ENABLED", impressions=2000)
        ctx = _ctx(campaigns=[c], audience_performance=[])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ADD_AUDIENCE_SIGNALS
        assert recs[0].severity == RecommendationSeverity.LOW

    def test_campaign_with_audience_not_triggered(self):
        c = _campaign(campaign_id=1, channel_type="SEARCH", status="ENABLED", impressions=2000)
        aud = _audience_perf(campaign_id=1)
        ctx = _ctx(campaigns=[c], audience_performance=[aud])
        assert self.rule.detect(ctx) == []

    def test_non_search_campaign_not_triggered(self):
        c = _campaign(campaign_id=1, channel_type="DISPLAY", status="ENABLED", impressions=2000)
        ctx = _ctx(campaigns=[c], audience_performance=[])
        assert self.rule.detect(ctx) == []

    def test_low_impressions_not_triggered(self):
        c = _campaign(campaign_id=1, channel_type="SEARCH", status="ENABLED", impressions=500)
        ctx = _ctx(campaigns=[c], audience_performance=[])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_not_triggered(self):
        c = _campaign(campaign_id=1, channel_type="SEARCH", status="PAUSED", impressions=2000)
        ctx = _ctx(campaigns=[c], audience_performance=[])
        assert self.rule.detect(ctx) == []

    def test_multiple_eligible_campaigns(self):
        c1 = _campaign(campaign_id=1, channel_type="SEARCH", status="ENABLED", impressions=2000)
        c2 = _campaign(campaign_id=2, channel_type="SEARCH", status="ENABLED", impressions=1500)
        ctx = _ctx(campaigns=[c1, c2], audience_performance=[])
        assert len(self.rule.detect(ctx)) == 2


# ===========================================================================
# Rule 33 - ReallocateBudgetRule
# ===========================================================================


class TestReallocateBudgetRule:
    rule = ReallocateBudgetRule()

    def _high_roas_constrained(self, campaign_id: int = 1) -> CampaignSnapshot:
        """ROAS=4.0, budget utilisation=98% (constrained)."""
        return _campaign(
            campaign_id=campaign_id,
            cost_micros=19_600_000,   # ~98% of budget
            budget_micros=20_000_000,
            conv_value=78.4,          # ROAS = 78.4 / 19.6 = 4.0
            status="ENABLED",
        )

    def _low_roas_underspending(self, campaign_id: int = 2) -> CampaignSnapshot:
        """ROAS=0.5, budget utilisation=30% (underspending)."""
        return _campaign(
            campaign_id=campaign_id,
            cost_micros=6_000_000,    # 30% of budget
            budget_micros=20_000_000,
            conv_value=3.0,           # ROAS = 3.0 / 6.0 = 0.5
            status="ENABLED",
        )

    def test_high_low_pair_triggers(self):
        high = self._high_roas_constrained()
        low = self._low_roas_underspending()
        ctx = _ctx(campaigns=[high, low])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.REALLOCATE_BUDGET
        assert recs[0].severity == RecommendationSeverity.CRITICAL
        assert recs[0].target["to_campaign_id"] == high.campaign_id
        assert recs[0].target["from_campaign_id"] == low.campaign_id

    def test_no_low_performer_no_trigger(self):
        high = self._high_roas_constrained()
        also_high = _campaign(
            campaign_id=2,
            cost_micros=18_000_000,
            budget_micros=20_000_000,
            conv_value=72.0,
            status="ENABLED",
        )
        ctx = _ctx(campaigns=[high, also_high])
        assert self.rule.detect(ctx) == []

    def test_no_high_performer_no_trigger(self):
        low1 = self._low_roas_underspending(campaign_id=1)
        low2 = self._low_roas_underspending(campaign_id=2)
        ctx = _ctx(campaigns=[low1, low2])
        assert self.rule.detect(ctx) == []

    def test_single_campaign_no_trigger(self):
        ctx = _ctx(campaigns=[self._high_roas_constrained()])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_ignored(self):
        high = self._high_roas_constrained()
        low = _campaign(
            campaign_id=2,
            cost_micros=6_000_000,
            budget_micros=20_000_000,
            conv_value=3.0,
            status="PAUSED",
        )
        ctx = _ctx(campaigns=[high, low])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 34 - IsLostToBudgetRule
# ===========================================================================


class TestIsLostToBudgetRule:
    rule = IsLostToBudgetRule()

    def test_budget_is_above_threshold_triggers(self):
        c = _campaign(
            campaign_id=1,
            status="ENABLED",
            search_budget_lost_impression_share=0.35,
        )
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.INCREASE_BUDGET
        assert recs[0].severity == RecommendationSeverity.HIGH
        # target includes signal key to distinguish from rule 07
        assert recs[0].target.get("signal") == "budget_is"

    def test_budget_is_below_threshold_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", search_budget_lost_impression_share=0.25)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_none_is_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", search_budget_lost_impression_share=None)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_no_trigger(self):
        c = _campaign(campaign_id=1, status="PAUSED", search_budget_lost_impression_share=0.50)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 35 - IsLostToRankRule
# ===========================================================================


class TestIsLostToRankRule:
    rule = IsLostToRankRule()

    def test_rank_is_above_threshold_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", search_rank_lost_impression_share=0.40)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.IMPROVE_QUALITY_SCORE
        assert recs[0].severity == RecommendationSeverity.HIGH

    def test_rank_is_below_threshold_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", search_rank_lost_impression_share=0.20)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_none_is_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", search_rank_lost_impression_share=None)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_no_trigger(self):
        c = _campaign(campaign_id=1, status="PAUSED", search_rank_lost_impression_share=0.50)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 36 - RelaxTargetCpaRule
# ===========================================================================


class TestRelaxTargetCpaRule:
    rule = RelaxTargetCpaRule()

    def test_too_tight_target_cpa_triggers(self):
        # Account avg CPA = 1_000_000; target = 300_000 (30% of avg → below 50% threshold)
        c = _campaign(
            campaign_id=1,
            status="ENABLED",
            bidding_strategy="TARGET_CPA",
            target_cpa_micros=300_000,
            cost_micros=10_000_000,
            conversions=2.0,
        )
        ctx = _ctx(campaigns=[c], history=_history(avg_cpa_micros=1_000_000, total_conv=50.0))
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.RELAX_TARGET_CPA
        assert recs[0].severity == RecommendationSeverity.MEDIUM
        assert recs[0].evidence["target_cpa_micros"] == 300_000

    def test_reasonable_target_cpa_no_trigger(self):
        # target = 700_000 (70% of avg → above 50% threshold)
        c = _campaign(
            campaign_id=1,
            status="ENABLED",
            bidding_strategy="TARGET_CPA",
            target_cpa_micros=700_000,
            cost_micros=10_000_000,
            conversions=2.0,
        )
        ctx = _ctx(campaigns=[c], history=_history(avg_cpa_micros=1_000_000, total_conv=50.0))
        assert self.rule.detect(ctx) == []

    def test_non_target_cpa_strategy_no_trigger(self):
        c = _campaign(
            campaign_id=1,
            status="ENABLED",
            bidding_strategy="MANUAL_CPC",
            target_cpa_micros=300_000,
            cost_micros=10_000_000,
            conversions=2.0,
        )
        ctx = _ctx(campaigns=[c], history=_history(avg_cpa_micros=1_000_000, total_conv=50.0))
        assert self.rule.detect(ctx) == []

    def test_no_target_cpa_micros_no_trigger(self):
        c = _campaign(
            campaign_id=1,
            status="ENABLED",
            bidding_strategy="TARGET_CPA",
            cost_micros=10_000_000,
            conversions=2.0,
        )
        ctx = _ctx(campaigns=[c], history=_history(avg_cpa_micros=1_000_000, total_conv=50.0))
        assert self.rule.detect(ctx) == []

    def test_high_conversions_no_trigger(self):
        # Already achieving good results despite tight target — skip
        c = _campaign(
            campaign_id=1,
            status="ENABLED",
            bidding_strategy="TARGET_CPA",
            target_cpa_micros=300_000,
            cost_micros=10_000_000,
            conversions=10.0,  # > _MAX_CONVERSIONS threshold of 5
        )
        ctx = _ctx(campaigns=[c], history=_history(avg_cpa_micros=1_000_000, total_conv=50.0))
        assert self.rule.detect(ctx) == []

    def test_no_account_avg_cpa_no_trigger(self):
        c = _campaign(
            campaign_id=1,
            status="ENABLED",
            bidding_strategy="TARGET_CPA",
            target_cpa_micros=300_000,
            cost_micros=10_000_000,
            conversions=2.0,
        )
        ctx = _ctx(campaigns=[c], history=_history(avg_cpa_micros=0, total_conv=0.0))
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 37 - DiversifyChannelsRule
# ===========================================================================


class TestDiversifyChannelsRule:
    rule = DiversifyChannelsRule()

    def test_high_spend_growth_low_conv_growth_triggers(self):
        # Cost grew 30%, conversions flat
        prev = _campaign(campaign_id=1, cost_micros=20_000_000, conversions=10.0)
        curr = _campaign(campaign_id=1, cost_micros=26_000_000, conversions=10.5)
        ctx = _ctx(campaigns=[curr], prev_campaigns=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.DIVERSIFY_CHANNELS
        assert recs[0].severity == RecommendationSeverity.MEDIUM
        assert recs[0].evidence["cost_growth_pct"] == pytest.approx(30.0, abs=0.1)

    def test_low_spend_growth_no_trigger(self):
        # Cost grew only 10% — below 20% threshold
        prev = _campaign(campaign_id=1, cost_micros=20_000_000, conversions=10.0)
        curr = _campaign(campaign_id=1, cost_micros=22_000_000, conversions=9.0)
        ctx = _ctx(campaigns=[curr], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_strong_conv_growth_no_trigger(self):
        # Cost grew 30% AND conversions also grew 25% — healthy scaling
        prev = _campaign(campaign_id=1, cost_micros=20_000_000, conversions=10.0)
        curr = _campaign(campaign_id=1, cost_micros=26_000_000, conversions=12.5)
        ctx = _ctx(campaigns=[curr], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_prev_campaigns_no_trigger(self):
        curr = _campaign(campaign_id=1, cost_micros=26_000_000, conversions=10.0)
        ctx = _ctx(campaigns=[curr], prev_campaigns=[])
        assert self.rule.detect(ctx) == []

    def test_low_absolute_spend_no_trigger(self):
        # Cost < _MIN_COST_MICROS threshold
        prev = _campaign(campaign_id=1, cost_micros=5_000_000, conversions=2.0)
        curr = _campaign(campaign_id=1, cost_micros=7_000_000, conversions=2.0)
        ctx = _ctx(campaigns=[curr], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_no_trigger(self):
        prev = _campaign(campaign_id=1, cost_micros=20_000_000, conversions=10.0)
        curr = _campaign(campaign_id=1, status="PAUSED", cost_micros=26_000_000, conversions=10.0)
        ctx = _ctx(campaigns=[curr], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Module 6 helpers
# ===========================================================================


def _conv_action(**kwargs) -> ConversionActionSnapshot:
    defaults = dict(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        conversion_action_id=1,
        name="Purchase",
        category="PURCHASE",
        counting_type="ONE_PER_CLICK",
        status="ENABLED",
        include_in_conversions_metric=True,
    )
    defaults.update(kwargs)
    return ConversionActionSnapshot(**defaults)


# ===========================================================================
# Rule 38 - UpgradeConversionActionRule
# ===========================================================================


class TestUpgradeConversionActionRule:
    rule = UpgradeConversionActionRule()

    def test_all_micro_page_view_triggers(self):
        ca = _conv_action(name="Page view", category="PAGE_VIEW")
        ctx = _ctx(conversion_actions=[ca])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.UPGRADE_CONVERSION_ACTION
        assert recs[0].severity == RecommendationSeverity.HIGH

    def test_all_micro_default_category_triggers(self):
        ca = _conv_action(name="Button click", category="DEFAULT")
        ctx = _ctx(conversion_actions=[ca])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_micro_name_signal_triggers(self):
        ca = _conv_action(name="Scroll depth 50%", category="UNKNOWN")
        ctx = _ctx(conversion_actions=[ca])
        assert len(self.rule.detect(ctx)) == 1

    def test_macro_purchase_present_no_trigger(self):
        micro = _conv_action(name="Page view", category="PAGE_VIEW")
        macro = _conv_action(conversion_action_id=2, name="Purchase", category="PURCHASE")
        ctx = _ctx(conversion_actions=[micro, macro])
        assert self.rule.detect(ctx) == []

    def test_lead_category_no_trigger(self):
        ca = _conv_action(name="Contact form", category="LEAD")
        ctx = _ctx(conversion_actions=[ca])
        assert self.rule.detect(ctx) == []

    def test_excluded_from_conversions_metric_ignored(self):
        # Action not included in Conversions column → don't count as tracked
        ca = _conv_action(
            name="Page view", category="PAGE_VIEW", include_in_conversions_metric=False
        )
        ctx = _ctx(conversion_actions=[ca])
        # No active included actions → no trigger (empty active list)
        assert self.rule.detect(ctx) == []

    def test_removed_action_ignored(self):
        ca = _conv_action(name="Page view", category="PAGE_VIEW", status="REMOVED")
        ctx = _ctx(conversion_actions=[ca])
        assert self.rule.detect(ctx) == []

    def test_empty_no_trigger(self):
        ctx = _ctx(conversion_actions=[])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Rule 39 - DeduplicateConversionsRule
# ===========================================================================


class TestDeduplicateConversionsRule:
    rule = DeduplicateConversionsRule()

    def test_high_ratio_triggers(self):
        # all_conversions = 60, conversions = 10 → ratio = 6.0 > 5.0
        c = _campaign(campaign_id=1, status="ENABLED", conversions=10.0, all_conversions=60.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.DEDUPLICATE_CONVERSIONS
        assert recs[0].severity == RecommendationSeverity.HIGH
        assert recs[0].evidence["ratio"] == pytest.approx(6.0)

    def test_acceptable_ratio_no_trigger(self):
        # all_conversions = 30, conversions = 10 → ratio = 3.0 < 5.0
        c = _campaign(campaign_id=1, status="ENABLED", conversions=10.0, all_conversions=30.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_zero_conversions_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", conversions=0.0, all_conversions=0.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_paused_campaigns_excluded(self):
        c = _campaign(campaign_id=1, status="PAUSED", conversions=10.0, all_conversions=60.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_aggregates_across_campaigns(self):
        c1 = _campaign(campaign_id=1, status="ENABLED", conversions=5.0, all_conversions=30.0)
        c2 = _campaign(campaign_id=2, status="ENABLED", conversions=5.0, all_conversions=30.0)
        ctx = _ctx(campaigns=[c1, c2])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].evidence["ratio"] == pytest.approx(6.0)


# ===========================================================================
# Rule 40 - SetConversionValueRule
# ===========================================================================


class TestSetConversionValueRule:
    rule = SetConversionValueRule()

    def test_conversions_no_value_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", conversions=15.0, conv_value=0.0)
        ctx = _ctx(campaigns=[c])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.SET_CONVERSION_VALUE
        assert recs[0].severity == RecommendationSeverity.MEDIUM

    def test_has_conv_value_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", conversions=15.0, conv_value=500.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_insufficient_conversions_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", conversions=5.0, conv_value=0.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_paused_campaigns_excluded(self):
        c = _campaign(campaign_id=1, status="PAUSED", conversions=15.0, conv_value=0.0)
        ctx = _ctx(campaigns=[c])
        assert self.rule.detect(ctx) == []

    def test_aggregates_across_campaigns(self):
        c1 = _campaign(campaign_id=1, status="ENABLED", conversions=6.0, conv_value=0.0)
        c2 = _campaign(campaign_id=2, status="ENABLED", conversions=6.0, conv_value=0.0)
        ctx = _ctx(campaigns=[c1, c2])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_one_campaign_has_value_no_trigger(self):
        c1 = _campaign(campaign_id=1, status="ENABLED", conversions=10.0, conv_value=200.0)
        c2 = _campaign(campaign_id=2, status="ENABLED", conversions=5.0, conv_value=0.0)
        ctx = _ctx(campaigns=[c1, c2])
        # total conv_value = 200 > 0 → no trigger
        assert self.rule.detect(ctx) == []


# ---------------------------------------------------------------------------
# Helpers for Module 7
# ---------------------------------------------------------------------------


def _ext(campaign_id: int = 1, extension_type: str = "SITELINK") -> CampaignExtensionSnapshot:
    return CampaignExtensionSnapshot(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=campaign_id,
        extension_type=extension_type,
    )


def _sitelink_perf(
    campaign_id: int = 1,
    asset_id: int = 100,
    impressions: int = 600,
    clicks: int = 1,
) -> SitelinkPerformanceSnapshot:
    return SitelinkPerformanceSnapshot(
        id=_sid(),
        account_id=_ACCOUNT_ID,
        snapshot_date=_SNAP_DATE,
        campaign_id=campaign_id,
        asset_id=asset_id,
        impressions=impressions,
        clicks=clicks,
    )


# ---------------------------------------------------------------------------
# Rule 41 — Add Sitelinks
# ---------------------------------------------------------------------------


class TestAddSitelinksRule:
    rule = AddSitelinksRule()

    def test_no_sitelink_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ADD_SITELINKS
        assert recs[0].target["campaign_id"] == 1

    def test_has_sitelink_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        ext = _ext(campaign_id=1, extension_type="SITELINK")
        ctx = _ctx(campaigns=[c], campaign_extensions=[ext])
        assert self.rule.detect(ctx) == []

    def test_other_extension_type_still_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        # Has CALLOUT but not SITELINK
        ext = _ext(campaign_id=1, extension_type="CALLOUT")
        ctx = _ctx(campaigns=[c], campaign_extensions=[ext])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_below_min_impressions_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=500)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_no_trigger(self):
        c = _campaign(campaign_id=1, status="PAUSED", impressions=2_000)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        assert self.rule.detect(ctx) == []


# ---------------------------------------------------------------------------
# Rule 42 — Add Callouts
# ---------------------------------------------------------------------------


class TestAddCalloutsRule:
    rule = AddCalloutsRule()

    def test_no_callout_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ADD_CALLOUTS

    def test_has_callout_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        ext = _ext(campaign_id=1, extension_type="CALLOUT")
        ctx = _ctx(campaigns=[c], campaign_extensions=[ext])
        assert self.rule.detect(ctx) == []

    def test_below_impressions_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=999)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        assert self.rule.detect(ctx) == []

    def test_paused_campaign_no_trigger(self):
        c = _campaign(campaign_id=1, status="PAUSED", impressions=5_000)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        assert self.rule.detect(ctx) == []


# ---------------------------------------------------------------------------
# Rule 43 — Add Structured Snippets
# ---------------------------------------------------------------------------


class TestAddStructuredSnippetsRule:
    rule = AddStructuredSnippetsRule()

    def test_no_snippets_triggers(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.ADD_STRUCTURED_SNIPPETS

    def test_has_snippet_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        ext = _ext(campaign_id=1, extension_type="STRUCTURED_SNIPPET")
        ctx = _ctx(campaigns=[c], campaign_extensions=[ext])
        assert self.rule.detect(ctx) == []

    def test_sitelink_does_not_satisfy(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=2_000)
        ext = _ext(campaign_id=1, extension_type="SITELINK")
        ctx = _ctx(campaigns=[c], campaign_extensions=[ext])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1

    def test_below_impressions_no_trigger(self):
        c = _campaign(campaign_id=1, status="ENABLED", impressions=100)
        ctx = _ctx(campaigns=[c], campaign_extensions=[])
        assert self.rule.detect(ctx) == []


# ---------------------------------------------------------------------------
# Rule 44 — Refresh Sitelink
# ---------------------------------------------------------------------------


class TestRefreshSitelinkRule:
    rule = RefreshSitelinkRule()

    def test_low_ctr_triggers(self):
        # 600 impressions, 1 click → CTR = 0.167% < 0.5%
        sl = _sitelink_perf(campaign_id=1, asset_id=100, impressions=600, clicks=1)
        ctx = _ctx(sitelink_performance=[sl])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.REFRESH_SITELINK
        assert recs[0].target["asset_id"] == 100

    def test_good_ctr_no_trigger(self):
        # 600 impressions, 10 clicks → CTR = 1.67% ≥ 0.5%
        sl = _sitelink_perf(campaign_id=1, asset_id=100, impressions=600, clicks=10)
        ctx = _ctx(sitelink_performance=[sl])
        assert self.rule.detect(ctx) == []

    def test_below_min_impressions_no_trigger(self):
        # 400 impressions < 500 minimum
        sl = _sitelink_perf(campaign_id=1, asset_id=100, impressions=400, clicks=0)
        ctx = _ctx(sitelink_performance=[sl])
        assert self.rule.detect(ctx) == []

    def test_aggregates_multiple_days(self):
        # Two days: 300 + 300 = 600 impressions, 0 + 0 = 0 clicks
        sl1 = _sitelink_perf(campaign_id=1, asset_id=200, impressions=300, clicks=0)
        sl2 = SitelinkPerformanceSnapshot(
            id=_sid(),
            account_id=_ACCOUNT_ID,
            snapshot_date=date(2026, 4, 8),
            campaign_id=1,
            asset_id=200,
            impressions=300,
            clicks=0,
        )
        ctx = _ctx(sitelink_performance=[sl1, sl2])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].evidence["impressions"] == 600

    def test_empty_sitelink_data_no_trigger(self):
        ctx = _ctx(sitelink_performance=[])
        assert self.rule.detect(ctx) == []

    def test_exactly_threshold_ctr_no_trigger(self):
        # CTR = 0.5% exactly → no trigger (must be strictly below)
        sl = _sitelink_perf(campaign_id=1, asset_id=100, impressions=1000, clicks=5)
        ctx = _ctx(sitelink_performance=[sl])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Module 1 — Performance Degradation & Trends (Rules 11–16)
# ===========================================================================


class TestCtrDeclineRule:
    """Rule 11: ad group CTR dropped >30% WoW with stable impressions."""

    rule = CtrDeclineRule()

    def test_triggers_on_significant_ctr_drop(self):
        # prev CTR = 5%, curr CTR = 3% → 40% drop with stable impressions
        ag = _ad_group(ad_group_id=10, impressions=500, clicks=15)   # CTR = 3%
        prev = _ad_group(ad_group_id=10, impressions=500, clicks=25)  # CTR = 5%
        ctx = _ctx(ad_groups=[ag], prev_ad_groups=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.CTR_DECLINE
        assert recs[0].evidence["ctr_drop_pct"] == pytest.approx(40.0, abs=1.0)

    def test_no_trigger_when_drop_below_threshold(self):
        # prev CTR = 5%, curr CTR = 4% → 20% drop (below 30% threshold)
        ag = _ad_group(ad_group_id=10, impressions=500, clicks=20)
        prev = _ad_group(ad_group_id=10, impressions=500, clicks=25)
        ctx = _ctx(ad_groups=[ag], prev_ad_groups=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_unstable(self):
        # Impressions changed >20%: 500 → 300 (40% drop)
        ag = _ad_group(ad_group_id=10, impressions=300, clicks=9)
        prev = _ad_group(ad_group_id=10, impressions=500, clicks=25)
        ctx = _ctx(ad_groups=[ag], prev_ad_groups=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        # 150 impressions < 200 minimum
        ag = _ad_group(ad_group_id=10, impressions=150, clicks=4)
        prev = _ad_group(ad_group_id=10, impressions=150, clicks=10)
        ctx = _ctx(ad_groups=[ag], prev_ad_groups=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_without_historical_data(self):
        ag = _ad_group(ad_group_id=10, impressions=500, clicks=10)
        ctx = _ctx(ad_groups=[ag], prev_ad_groups=[])
        assert self.rule.detect(ctx) == []


class TestCpaSpikeRule:
    """Rule 12: campaign CPA increased >50% WoW with ≥5 conversions in both periods."""

    rule = CpaSpikeRule()

    def test_triggers_on_cpa_spike(self):
        # prev: 10M cost / 10 conv = 1M CPA; curr: 20M cost / 10 conv = 2M CPA → 100% spike
        camp = _campaign(campaign_id=1, cost_micros=20_000_000, conversions=10.0)
        prev = _campaign(campaign_id=1, cost_micros=10_000_000, conversions=10.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.CPA_SPIKE
        assert recs[0].evidence["cpa_spike_pct"] == pytest.approx(100.0, abs=1.0)

    def test_no_trigger_when_spike_below_threshold(self):
        # prev: 10M / 10 = 1M CPA; curr: 13M / 10 = 1.3M CPA → 30% spike (below 50%)
        camp = _campaign(campaign_id=1, cost_micros=13_000_000, conversions=10.0)
        prev = _campaign(campaign_id=1, cost_micros=10_000_000, conversions=10.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_too_few_conversions(self):
        # Only 3 conversions in current period (below 5 minimum)
        camp = _campaign(campaign_id=1, cost_micros=20_000_000, conversions=3.0)
        prev = _campaign(campaign_id=1, cost_micros=10_000_000, conversions=10.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_without_historical_data(self):
        camp = _campaign(campaign_id=1, cost_micros=20_000_000, conversions=10.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[])
        assert self.rule.detect(ctx) == []


class TestConversionRateDropRule:
    """Rule 13: campaign click-to-conversion rate dropped >25% WoW with ≥50 clicks."""

    rule = ConversionRateDropRule()

    def test_triggers_on_cvr_drop(self):
        # prev: 5 conv / 100 clicks = 5% CVR; curr: 3 conv / 100 clicks = 3% CVR → 40% drop
        camp = _campaign(campaign_id=1, clicks=100, conversions=3.0, cost_micros=5_000_000)
        prev = _campaign(campaign_id=1, clicks=100, conversions=5.0, cost_micros=5_000_000)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.CONVERSION_RATE_DROP
        assert recs[0].evidence["cvr_drop_pct"] == pytest.approx(40.0, abs=1.0)

    def test_no_trigger_when_drop_below_threshold(self):
        # 5% CVR → 4.5% CVR → 10% drop (below 25%)
        camp = _campaign(campaign_id=1, clicks=100, conversions=4.5, cost_micros=5_000_000)
        prev = _campaign(campaign_id=1, clicks=100, conversions=5.0, cost_micros=5_000_000)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_too_few_clicks(self):
        # Only 30 clicks in current period (below 50 minimum)
        camp = _campaign(campaign_id=1, clicks=30, conversions=1.0, cost_micros=2_000_000)
        prev = _campaign(campaign_id=1, clicks=100, conversions=5.0, cost_micros=5_000_000)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_without_historical_data(self):
        camp = _campaign(campaign_id=1, clicks=100, conversions=3.0, cost_micros=5_000_000)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[])
        assert self.rule.detect(ctx) == []


class TestImpressionShareErosionRule:
    """Rule 14: search IS dropped >15 pp WoW, current IS < 85%."""

    rule = ImpressionShareErosionRule()

    def test_triggers_on_large_is_drop(self):
        # IS dropped from 70% to 45% — 25 pp drop, current IS below 85%
        camp = _campaign(campaign_id=1, search_impression_share=0.45)
        prev = _campaign(campaign_id=1, search_impression_share=0.70)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.IMPRESSION_SHARE_EROSION
        assert recs[0].evidence["drop_pp"] == pytest.approx(0.25, abs=0.001)

    def test_no_trigger_when_drop_below_threshold(self):
        # IS dropped from 70% to 60% — 10 pp drop (below 15 pp threshold)
        camp = _campaign(campaign_id=1, search_impression_share=0.60)
        prev = _campaign(campaign_id=1, search_impression_share=0.70)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_current_is_above_ceiling(self):
        # IS dropped from 95% to 86% — 9 pp drop and current IS > 85%
        camp = _campaign(campaign_id=1, search_impression_share=0.86)
        prev = _campaign(campaign_id=1, search_impression_share=0.95)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_is_data_missing(self):
        camp = _campaign(campaign_id=1, search_impression_share=None)
        prev = _campaign(campaign_id=1, search_impression_share=0.70)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_without_historical_data(self):
        camp = _campaign(campaign_id=1, search_impression_share=0.45)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[])
        assert self.rule.detect(ctx) == []


class TestSpendAccelerationRule:
    """Rule 15: spend grew >30% WoW but conversions stayed flat/declined."""

    rule = SpendAccelerationRule()

    def test_triggers_on_spend_acceleration_without_results(self):
        # Spend: 5M → 8M (+60%), conversions: 5 → 5 (0% change)
        camp = _campaign(campaign_id=1, cost_micros=8_000_000, conversions=5.0)
        prev = _campaign(campaign_id=1, cost_micros=5_000_000, conversions=5.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.SPEND_ACCELERATION
        assert recs[0].estimated_monthly_savings_micros == (8_000_000 - 5_000_000) * 4

    def test_no_trigger_when_conversions_grew_proportionally(self):
        # Spend +50%, conversions +50% — conversion growth > 10% threshold
        camp = _campaign(campaign_id=1, cost_micros=7_500_000, conversions=7.5)
        prev = _campaign(campaign_id=1, cost_micros=5_000_000, conversions=5.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_spend_growth_below_threshold(self):
        # Spend: 5M → 6M (+20%, below 30% threshold)
        camp = _campaign(campaign_id=1, cost_micros=6_000_000, conversions=5.0)
        prev = _campaign(campaign_id=1, cost_micros=5_000_000, conversions=5.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_spend_below_minimum(self):
        # Spend 4M micros (below 5M threshold)
        camp = _campaign(campaign_id=1, cost_micros=4_000_000, conversions=1.0)
        prev = _campaign(campaign_id=1, cost_micros=4_000_000, conversions=1.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_without_historical_data(self):
        camp = _campaign(campaign_id=1, cost_micros=8_000_000, conversions=5.0)
        ctx = _ctx(campaigns=[camp], prev_campaigns=[])
        assert self.rule.detect(ctx) == []


class TestQualityScoreDeteriorationRule:
    """Rule 16: keyword QS dropped ≥2 points vs. 7-day-ago snapshot."""

    rule = QualityScoreDeteriorationRule()

    def test_triggers_on_qs_drop(self):
        # QS dropped from 8 to 5 — a 3-point drop with sufficient spend
        kw = _keyword(criterion_id=100, ad_group_id=10, quality_score=5, cost_micros=3_000_000)
        prev = _keyword(criterion_id=100, ad_group_id=10, quality_score=8, cost_micros=3_000_000)
        ctx = _ctx(keywords=[kw], prev_keywords=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.QUALITY_SCORE_DETERIORATION
        assert recs[0].evidence["qs_drop"] == 3

    def test_no_trigger_when_drop_below_minimum(self):
        # QS dropped from 8 to 7 — only 1 point (below 2-point threshold)
        kw = _keyword(criterion_id=100, ad_group_id=10, quality_score=7, cost_micros=3_000_000)
        prev = _keyword(criterion_id=100, ad_group_id=10, quality_score=8, cost_micros=3_000_000)
        ctx = _ctx(keywords=[kw], prev_keywords=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_spend_too_low(self):
        # QS dropped 3 points but cost is only 1M (below 2M threshold)
        kw = _keyword(criterion_id=100, ad_group_id=10, quality_score=5, cost_micros=1_000_000)
        prev = _keyword(criterion_id=100, ad_group_id=10, quality_score=8, cost_micros=1_000_000)
        ctx = _ctx(keywords=[kw], prev_keywords=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_no_quality_score(self):
        kw = _keyword(criterion_id=100, ad_group_id=10, quality_score=None, cost_micros=3_000_000)
        prev = _keyword(criterion_id=100, ad_group_id=10, quality_score=8, cost_micros=3_000_000)
        ctx = _ctx(keywords=[kw], prev_keywords=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_without_historical_data(self):
        kw = _keyword(criterion_id=100, ad_group_id=10, quality_score=5, cost_micros=3_000_000)
        ctx = _ctx(keywords=[kw], prev_keywords=[])
        assert self.rule.detect(ctx) == []


# ===========================================================================
# Module 2 — Ad Copy & Creative Intelligence (Rules 17–22)
# ===========================================================================


def _rsa_ad(**kwargs) -> AdSnapshot:
    """Helper: return an enabled RSA ad with sensible defaults."""
    defaults = dict(
        type="RESPONSIVE_SEARCH_AD",
        status="ENABLED",
        impressions=300,
        headlines_json='["Buy Now", "Fast Delivery", "Best Price"]',
        descriptions_json='["We guarantee satisfaction.", "Call us today."]',
        ad_strength=None,
    )
    defaults.update(kwargs)
    return _ad(**defaults)


class TestAdKeywordMismatchRule:
    """Rule 17: keyword tokens cover <35% of ad headlines."""

    rule = AdKeywordMismatchRule()

    def test_triggers_when_keyword_tokens_absent_from_headlines(self):
        # Keywords about "shoes running sport" but headlines say completely different things
        ag = _ad_group(ad_group_id=10, impressions=300)
        kw = _keyword(ad_group_id=10, text="running shoes sport", impressions=300, status="ENABLED")
        ad = _rsa_ad(
            ad_group_id=10,
            impressions=300,
            headlines_json='["Great Deals", "Premium Service", "Free Shipping"]',
        )
        ctx = _ctx(ad_groups=[ag], keywords=[kw], ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.AD_KEYWORD_MISMATCH

    def test_no_trigger_when_keywords_covered(self):
        # Keyword "running shoes" appears in headlines
        ag = _ad_group(ad_group_id=10, impressions=300)
        kw = _keyword(ad_group_id=10, text="running shoes", impressions=300, status="ENABLED")
        ad = _rsa_ad(
            ad_group_id=10,
            impressions=300,
            headlines_json='["Buy Running Shoes", "Top Running Shoes", "Running Shoes Sale"]',
        )
        ctx = _ctx(ad_groups=[ag], keywords=[kw], ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        ag = _ad_group(ad_group_id=10, impressions=150)
        kw = _keyword(ad_group_id=10, text="shoes", impressions=150, status="ENABLED")
        ad = _rsa_ad(ad_group_id=10, impressions=150, headlines_json='["Deals"]')
        ctx = _ctx(ad_groups=[ag], keywords=[kw], ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_no_rsa_ads(self):
        ag = _ad_group(ad_group_id=10, impressions=300)
        kw = _keyword(ad_group_id=10, text="shoes", impressions=300, status="ENABLED")
        non_rsa = _ad(ad_group_id=10, type="EXPANDED_TEXT_AD", status="ENABLED", impressions=300)
        ctx = _ctx(ad_groups=[ag], keywords=[kw], ads=[non_rsa])
        assert self.rule.detect(ctx) == []


class TestMissingCtaRule:
    """Rule 18: RSA ad has no call-to-action verb in its copy."""

    rule = MissingCtaRule()

    def test_triggers_when_no_cta_present(self):
        ad = _rsa_ad(
            ad_id=200,
            impressions=200,
            headlines_json='["High Quality", "Premium Service", "Best Value"]',
            descriptions_json='["We are the best.", "Top-notch quality for you."]',
        )
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.MISSING_CTA

    def test_no_trigger_when_cta_present_in_headline(self):
        ad = _rsa_ad(
            ad_id=200,
            impressions=200,
            headlines_json='["Buy Now", "Premium Service", "Best Value"]',
            descriptions_json='["We are the best.", "Top-notch quality."]',
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_cta_present_in_description(self):
        ad = _rsa_ad(
            ad_id=200,
            impressions=200,
            headlines_json='["Premium Service"]',
            descriptions_json='["Get a free quote today."]',
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        ad = _rsa_ad(
            ad_id=200,
            impressions=50,
            headlines_json='["High Quality"]',
            descriptions_json='["We are the best."]',
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_for_non_rsa_ad(self):
        ad = _ad(
            ad_id=200,
            type="EXPANDED_TEXT_AD",
            status="ENABLED",
            impressions=200,
            headlines_json='["High Quality"]',
            descriptions_json='["We are the best."]',
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []


class TestWeakRsaStrengthRule:
    """Rule 19: RSA ad_strength is POOR/AVERAGE or has fewer than 8 unique headlines."""

    rule = WeakRsaStrengthRule()

    def test_triggers_on_poor_ad_strength(self):
        ad = _rsa_ad(
            ad_id=200,
            impressions=200,
            ad_strength="POOR",
            headlines_json='["A", "B", "C", "D", "E", "F", "G", "H", "I"]',
        )
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.WEAK_RSA_STRENGTH
        assert "ad_strength=POOR" in recs[0].evidence["reason"]

    def test_triggers_on_average_ad_strength(self):
        ad = _rsa_ad(ad_id=200, impressions=200, ad_strength="AVERAGE",
                     headlines_json='["A", "B", "C", "D", "E", "F", "G", "H"]')
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert "ad_strength=AVERAGE" in recs[0].evidence["reason"]

    def test_triggers_when_too_few_unique_headlines(self):
        # Only 5 unique headlines — below the 8-minimum threshold
        headlines = ["Buy Now", "Great Deals", "Fast Delivery", "Free Shipping", "Best Price"]
        ad = _rsa_ad(ad_id=200, impressions=200, ad_strength="GOOD",
                     headlines_json=str(headlines).replace("'", '"'))
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert "unique headlines" in recs[0].evidence["reason"]

    def test_no_trigger_when_good_strength_and_enough_headlines(self):
        headlines = [f"Headline {i}" for i in range(9)]
        import json
        ad = _rsa_ad(ad_id=200, impressions=200, ad_strength="GOOD",
                     headlines_json=json.dumps(headlines))
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        ad = _rsa_ad(ad_id=200, impressions=50, ad_strength="POOR",
                     headlines_json='["A", "B"]')
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []


class TestAdFatigueRule:
    """Rule 20: ad CTR dropped >25% WoW with stable impression volume."""

    rule = AdFatigueRule()

    def test_triggers_on_ctr_drop(self):
        # prev CTR = 4%, curr CTR = 2.5% → 37.5% drop with stable impressions
        ad = _ad(ad_id=200, status="ENABLED", impressions=600, clicks=15,
                 cost_micros=1_000_000, conversions=0.1)
        prev = _ad(ad_id=200, status="ENABLED", impressions=600, clicks=24,
                   cost_micros=1_000_000, conversions=0.1)
        ctx = _ctx(ads=[ad], prev_ads=[prev])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.AD_FATIGUE
        assert recs[0].evidence["ctr_drop_pct"] == pytest.approx(37.5, abs=1.0)

    def test_no_trigger_when_drop_below_threshold(self):
        # prev CTR = 4%, curr CTR = 3.5% → 12.5% drop (below 25%)
        ad = _ad(ad_id=200, status="ENABLED", impressions=600, clicks=21,
                 cost_micros=1_000_000, conversions=0.1)
        prev = _ad(ad_id=200, status="ENABLED", impressions=600, clicks=24,
                   cost_micros=1_000_000, conversions=0.1)
        ctx = _ctx(ads=[ad], prev_ads=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_unstable(self):
        # Impressions: 600 → 300 (50% drop — unstable)
        ad = _ad(ad_id=200, status="ENABLED", impressions=300, clicks=6,
                 cost_micros=1_000_000, conversions=0.1)
        prev = _ad(ad_id=200, status="ENABLED", impressions=600, clicks=24,
                   cost_micros=1_000_000, conversions=0.1)
        ctx = _ctx(ads=[ad], prev_ads=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        # 400 impressions < 500 minimum
        ad = _ad(ad_id=200, status="ENABLED", impressions=400, clicks=8,
                 cost_micros=1_000_000, conversions=0.1)
        prev = _ad(ad_id=200, status="ENABLED", impressions=400, clicks=16,
                   cost_micros=1_000_000, conversions=0.1)
        ctx = _ctx(ads=[ad], prev_ads=[prev])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_without_historical_data(self):
        ad = _ad(ad_id=200, status="ENABLED", impressions=600, clicks=15,
                 cost_micros=1_000_000, conversions=0.1)
        ctx = _ctx(ads=[ad], prev_ads=[])
        assert self.rule.detect(ctx) == []


class TestRedundantHeadlinesRule:
    """Rule 21: ≥3 RSA headlines share >60% Jaccard token overlap."""

    rule = RedundantHeadlinesRule()

    def test_triggers_on_very_similar_headlines(self):
        import json
        # Three nearly identical headlines — all share the same core tokens
        headlines = [
            "Best Running Shoes Online",
            "Top Running Shoes Online",
            "Great Running Shoes Online",
        ]
        ad = _rsa_ad(ad_id=200, impressions=200, headlines_json=json.dumps(headlines))
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.REDUNDANT_HEADLINES

    def test_no_trigger_when_headlines_are_diverse(self):
        import json
        headlines = [
            "Buy Running Shoes",
            "Free Next Day Delivery",
            "Money Back Guarantee",
        ]
        ad = _rsa_ad(ad_id=200, impressions=200, headlines_json=json.dumps(headlines))
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        import json
        headlines = ["Best Shoes Online", "Top Shoes Online", "Great Shoes Online"]
        ad = _rsa_ad(ad_id=200, impressions=50, headlines_json=json.dumps(headlines))
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_fewer_than_3_headlines(self):
        import json
        ad = _rsa_ad(ad_id=200, impressions=200,
                     headlines_json=json.dumps(["Best Shoes", "Top Shoes"]))
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []


class TestGenericDescriptionRule:
    """Rule 22: all RSA descriptions lack numbers, currency, percentages, or anchor words."""

    rule = GenericDescriptionRule()

    def test_triggers_when_all_descriptions_generic(self):
        import json
        ad = _rsa_ad(
            ad_id=200,
            impressions=300,
            descriptions_json=json.dumps([
                "We are the best service provider.",
                "High quality solutions for your business.",
            ]),
        )
        ctx = _ctx(ads=[ad])
        recs = self.rule.detect(ctx)
        assert len(recs) == 1
        assert recs[0].kind == RecommendationKind.GENERIC_DESCRIPTION

    def test_no_trigger_when_description_contains_number(self):
        import json
        ad = _rsa_ad(
            ad_id=200,
            impressions=300,
            descriptions_json=json.dumps(["We have over 1000 satisfied customers."]),
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_description_contains_percentage(self):
        import json
        ad = _rsa_ad(
            ad_id=200,
            impressions=300,
            descriptions_json=json.dumps(["Save 30% on your first order."]),
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_description_contains_anchor_word(self):
        import json
        ad = _rsa_ad(
            ad_id=200,
            impressions=300,
            descriptions_json=json.dumps(["Full money-back guarantee."]),
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_when_impressions_below_minimum(self):
        import json
        ad = _rsa_ad(
            ad_id=200,
            impressions=100,
            descriptions_json=json.dumps(["Generic description text."]),
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []

    def test_no_trigger_for_non_rsa_ad(self):
        import json
        ad = _ad(
            ad_id=200,
            type="EXPANDED_TEXT_AD",
            status="ENABLED",
            impressions=300,
            headlines_json="[]",
            descriptions_json=json.dumps(["Generic description."]),
        )
        ctx = _ctx(ads=[ad])
        assert self.rule.detect(ctx) == []
