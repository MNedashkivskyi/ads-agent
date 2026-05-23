"""Unit tests for TierStructureConfig and tier-aware validator."""

from __future__ import annotations

from adcopilot.domain.launch.budget_tier import BudgetTier
from adcopilot.domain.launch.structure_rules import (
    TIER_CONFIGS,
    build_structure_prompt_fragment,
    get_structure_config,
)


class TestTierConfigs:
    def test_all_tiers_have_config(self) -> None:
        for tier in BudgetTier:
            assert tier in TIER_CONFIGS

    def test_micro_max_2_ad_groups(self) -> None:
        cfg = get_structure_config(BudgetTier.MICRO)
        assert cfg.max_ad_groups == 2

    def test_micro_no_broad_match(self) -> None:
        cfg = get_structure_config(BudgetTier.MICRO)
        assert not cfg.include_broad_match
        assert "broad" not in cfg.allowed_match_types

    def test_micro_no_intent_segmentation(self) -> None:
        cfg = get_structure_config(BudgetTier.MICRO)
        assert not cfg.require_intent_segmentation

    def test_micro_max_10_keywords(self) -> None:
        cfg = get_structure_config(BudgetTier.MICRO)
        assert cfg.max_keywords_per_group == 10

    def test_mid_requires_intent_segmentation(self) -> None:
        cfg = get_structure_config(BudgetTier.MID)
        assert cfg.require_intent_segmentation

    def test_mid_no_broad_match(self) -> None:
        cfg = get_structure_config(BudgetTier.MID)
        assert not cfg.include_broad_match

    def test_growth_includes_broad_match(self) -> None:
        cfg = get_structure_config(BudgetTier.GROWTH)
        assert cfg.include_broad_match
        assert "broad" in cfg.allowed_match_types

    def test_growth_min_3_ad_groups(self) -> None:
        cfg = get_structure_config(BudgetTier.GROWTH)
        assert cfg.min_ad_groups == 3

    def test_growth_max_6_ad_groups(self) -> None:
        cfg = get_structure_config(BudgetTier.GROWTH)
        assert cfg.max_ad_groups == 6

    def test_growth_requires_intent_segmentation(self) -> None:
        cfg = get_structure_config(BudgetTier.GROWTH)
        assert cfg.require_intent_segmentation


class TestPromptFragment:
    def test_micro_mentions_no_broad(self) -> None:
        fragment = build_structure_prompt_fragment(BudgetTier.MICRO)
        assert "broad" in fragment.lower()
        assert "Do NOT" in fragment

    def test_growth_does_not_say_no_broad(self) -> None:
        fragment = build_structure_prompt_fragment(BudgetTier.GROWTH)
        assert "Do NOT use broad" not in fragment

    def test_mid_mentions_intent_segmentation(self) -> None:
        fragment = build_structure_prompt_fragment(BudgetTier.MID)
        assert "intent" in fragment.lower()

    def test_fragment_is_string(self) -> None:
        for tier in BudgetTier:
            assert isinstance(build_structure_prompt_fragment(tier), str)
