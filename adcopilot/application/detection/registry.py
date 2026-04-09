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
from adcopilot.application.ports.recommendation_repository import RecommendationRepository


def build_rule_engine(rec_repo: RecommendationRepository) -> RuleEngine:
    """Instantiate all detection rules and return a configured RuleEngine."""
    rules: list[DetectionRule] = [
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
    ]
    return RuleEngine(rules=rules, rec_repo=rec_repo)
