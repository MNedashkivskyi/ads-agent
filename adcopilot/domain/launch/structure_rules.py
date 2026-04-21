"""Tier-specific campaign structure constraints.

Used by the LLM pipeline (Stage 2 prompt) and the validator to enforce
budget-appropriate ad group counts, keyword counts, and match-type restrictions.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.launch.budget_tier import BudgetTier


@dataclass(frozen=True)
class TierStructureConfig:
    """Constraints that control campaign structure for a given budget tier."""

    min_ad_groups: int
    max_ad_groups: int
    min_keywords_per_group: int
    max_keywords_per_group: int
    allowed_match_types: list[str]
    require_intent_segmentation: bool
    """If True, the LLM is instructed to create separate high-intent/mid-intent groups."""
    include_broad_match: bool
    """If True, broad-match keywords are included alongside exact/phrase."""


TIER_CONFIGS: dict[BudgetTier, TierStructureConfig] = {
    BudgetTier.MICRO: TierStructureConfig(
        min_ad_groups=1,
        max_ad_groups=2,
        min_keywords_per_group=5,
        max_keywords_per_group=10,
        allowed_match_types=["exact", "phrase"],
        require_intent_segmentation=False,
        include_broad_match=False,
    ),
    BudgetTier.MID: TierStructureConfig(
        min_ad_groups=2,
        max_ad_groups=4,
        min_keywords_per_group=8,
        max_keywords_per_group=12,
        allowed_match_types=["exact", "phrase", "broad"],
        require_intent_segmentation=True,
        include_broad_match=False,
    ),
    BudgetTier.GROWTH: TierStructureConfig(
        min_ad_groups=3,
        max_ad_groups=6,
        min_keywords_per_group=10,
        max_keywords_per_group=15,
        allowed_match_types=["exact", "phrase", "broad"],
        require_intent_segmentation=True,
        include_broad_match=True,
    ),
}


def get_structure_config(tier: BudgetTier) -> TierStructureConfig:
    """Return the :class:`TierStructureConfig` for the given tier."""
    return TIER_CONFIGS[tier]


def build_structure_prompt_fragment(tier: BudgetTier) -> str:
    """Return a natural-language constraint string for injection into the LLM prompt."""
    cfg = TIER_CONFIGS[tier]
    lines = [
        f"Budget tier: {tier.upper()} — apply the following structure constraints:",
        f"- Ad groups: {cfg.min_ad_groups}–{cfg.max_ad_groups} (no more, no fewer)",
        f"- Keywords per ad group: {cfg.min_keywords_per_group}–{cfg.max_keywords_per_group}",
        f"- Allowed match types: {', '.join(cfg.allowed_match_types)}",
    ]
    if not cfg.include_broad_match:
        lines.append("- Do NOT use broad match keywords.")
    if cfg.require_intent_segmentation:
        lines.append(
            "- Separate ad groups by search intent: create at least one HIGH-INTENT group "
            "(keywords containing 'buy', 'hire', 'book', 'order', 'price', 'cost') "
            "and one MID-INTENT group (keywords containing 'best', 'top', 'review', "
            "'compare', 'vs')."
        )
    return "\n".join(lines)
