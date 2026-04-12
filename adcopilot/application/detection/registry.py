"""Rule registry — assembles the RuleEngine with all active detection rules."""

from __future__ import annotations

from adcopilot.application.detection.base import DetectionRule
from adcopilot.application.detection.engine import RuleEngine
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
from adcopilot.application.detection.rules.rule_15_spend_acceleration import (
    SpendAccelerationRule,
)
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
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.snooze_repository import SnoozeRepository


def build_rule_engine(
    rec_repo: RecommendationRepository,
    snooze_repo: SnoozeRepository | None = None,
) -> RuleEngine:
    """Instantiate all detection rules and return a configured RuleEngine."""
    rules: list[DetectionRule] = [
        # Module 0 — Hygiene
        WastedSearchTermRule(),
        ZeroConversionKeywordRule(),
        LowQualityScoreKeywordRule(),
        DisapprovedAdRule(),
        BroadMatchBleedingRule(),
        NoConversionTrackingRule(),
        BudgetCappedRule(),
        SingleAdInGroupRule(),
        DeadKeywordRule(),
        WrongBiddingStrategyRule(),
        # Module 1 — Performance degradation & trends
        CtrDeclineRule(),
        CpaSpikeRule(),
        ConversionRateDropRule(),
        ImpressionShareErosionRule(),
        SpendAccelerationRule(),
        QualityScoreDeteriorationRule(),
        # Module 2 — Ad copy & creative intelligence
        AdKeywordMismatchRule(),
        MissingCtaRule(),
        WeakRsaStrengthRule(),
        AdFatigueRule(),
        RedundantHeadlinesRule(),
        GenericDescriptionRule(),
        # Module 3 — Campaign structure & organisation
        OverstuffedAdGroupRule(),
        KeywordCannibalizationRule(),
        NegativeKeywordConflictRule(),
        OrphanedCampaignRule(),
        MatchTypeRedundancyRule(),
        # Module 4 — Audience & targeting intelligence
        DeviceBidAdjustmentRule(),
        GeoExclusionRule(),
        AdScheduleAdjustmentRule(),
        DayOfWeekBidAdjustmentRule(),
        AddAudienceSignalsRule(),
        # Module 5 — Budget & bidding strategy
        ReallocateBudgetRule(),
        IsLostToBudgetRule(),
        IsLostToRankRule(),
        RelaxTargetCpaRule(),
        DiversifyChannelsRule(),
        # Module 6 — Conversion tracking & measurement
        UpgradeConversionActionRule(),
        DeduplicateConversionsRule(),
        SetConversionValueRule(),
    ]
    return RuleEngine(rules=rules, rec_repo=rec_repo, snooze_repo=snooze_repo)
