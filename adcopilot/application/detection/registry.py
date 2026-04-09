"""Rule registry — assembles the RuleEngine with all active detection rules."""

from __future__ import annotations

from adcopilot.application.detection.base import DetectionRule
from adcopilot.application.detection.engine import RuleEngine
from adcopilot.application.ports.recommendation_repository import RecommendationRepository


def build_rule_engine(rec_repo: RecommendationRepository) -> RuleEngine:
    """Instantiate all detection rules and return a configured RuleEngine.

    Rules are registered in Task 3.3. This stub keeps Task 3.2 importable.
    """
    rules: list[DetectionRule] = []  # populated in Task 3.3
    return RuleEngine(rules=rules, rec_repo=rec_repo)
