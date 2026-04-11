from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

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
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, UserId
from adcopilot.domain.recommendation import RecommendationKind, RecommendationSeverity
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
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
