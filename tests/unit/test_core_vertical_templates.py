"""Unit tests for all 7 core vertical YAML templates (Task 1.3).

Validates that every template file loads, meets structural requirements,
and contains the required Polish-language content.
"""

from __future__ import annotations

import pytest

from adcopilot.infrastructure.vertical_templates.yaml_adapter import YamlVerticalTemplateAdapter

REQUIRED_VERTICAL_IDS = {
    "beauty_salon",
    "dental_clinic",
    "law_firm",
    "restaurant",
    "auto_repair",
    "cleaning_service",
    "generic",
}

UNIVERSAL_NEGATIVES = {"darmowy", "praca", "kurs", "szkolenie", "jak zrobić"}
BUDGET_TIERS = {"micro", "mid", "growth"}


@pytest.fixture(scope="module")
def adapter() -> YamlVerticalTemplateAdapter:
    return YamlVerticalTemplateAdapter()


def test_all_required_verticals_load(adapter: YamlVerticalTemplateAdapter):
    loaded = {s.vertical_id for s in adapter.list_verticals()} | {"generic"}
    assert REQUIRED_VERTICAL_IDS.issubset(loaded), (
        f"Missing verticals: {REQUIRED_VERTICAL_IDS - loaded}"
    )


@pytest.mark.parametrize("vertical_id", sorted(REQUIRED_VERTICAL_IDS))
class TestEachVertical:
    def _get(self, adapter: YamlVerticalTemplateAdapter, vid: str):
        if vid == "generic":
            return adapter.get_default_template()
        t = adapter.get_template(vid)
        assert t is not None, f"Template '{vid}' not found"
        return t

    def test_has_at_least_two_ad_groups(
        self, vertical_id: str, adapter: YamlVerticalTemplateAdapter
    ):
        t = self._get(adapter, vertical_id)
        assert len(t.ad_groups) >= 2, (
            f"{vertical_id}: expected ≥2 ad groups, got {len(t.ad_groups)}"
        )

    def test_each_ad_group_has_at_least_eight_keywords(
        self, vertical_id: str, adapter: YamlVerticalTemplateAdapter
    ):
        t = self._get(adapter, vertical_id)
        for ag in t.ad_groups:
            assert len(ag.keyword_bank) >= 8, (
                f"{vertical_id} / '{ag.name_template}': "
                f"expected ≥8 keywords, got {len(ag.keyword_bank)}"
            )

    def test_universal_negatives_present(
        self, vertical_id: str, adapter: YamlVerticalTemplateAdapter
    ):
        t = self._get(adapter, vertical_id)
        all_neg = set(t.negatives.all_negatives)
        missing = UNIVERSAL_NEGATIVES - all_neg
        assert not missing, f"{vertical_id}: missing universal negatives {missing}"

    def test_all_budget_tiers_covered(self, vertical_id: str, adapter: YamlVerticalTemplateAdapter):
        t = self._get(adapter, vertical_id)
        for tier in BUDGET_TIERS:
            cfg = t.bidding_defaults.for_tier(tier)
            assert cfg.bidding_strategy, f"{vertical_id}: missing strategy for tier '{tier}'"

    def test_has_sitelinks(self, vertical_id: str, adapter: YamlVerticalTemplateAdapter):
        t = self._get(adapter, vertical_id)
        assert len(t.extensions.sitelinks) >= 2, f"{vertical_id}: expected ≥2 sitelinks"

    def test_has_callouts(self, vertical_id: str, adapter: YamlVerticalTemplateAdapter):
        t = self._get(adapter, vertical_id)
        assert len(t.extensions.callouts) >= 2, f"{vertical_id}: expected ≥2 callouts"

    def test_has_common_services(self, vertical_id: str, adapter: YamlVerticalTemplateAdapter):
        t = self._get(adapter, vertical_id)
        assert len(t.common_services) >= 1, f"{vertical_id}: expected at least 1 common service"

    def test_has_core_and_extended_keywords(
        self, vertical_id: str, adapter: YamlVerticalTemplateAdapter
    ):
        if vertical_id == "generic":
            pytest.skip("generic template is minimal by design")
        t = self._get(adapter, vertical_id)
        all_priorities = {kw.priority for ag in t.ad_groups for kw in ag.keyword_bank}
        assert "core" in {p.value for p in all_priorities}, f"{vertical_id}: no core keywords"
        assert "extended" in {p.value for p in all_priorities}, (
            f"{vertical_id}: no extended keywords"
        )

    def test_language_is_polish(self, vertical_id: str, adapter: YamlVerticalTemplateAdapter):
        t = self._get(adapter, vertical_id)
        assert t.language == "pl", f"{vertical_id}: expected language='pl', got '{t.language}'"

    def test_callout_lengths_within_limit(
        self, vertical_id: str, adapter: YamlVerticalTemplateAdapter
    ):
        t = self._get(adapter, vertical_id)
        for callout in t.extensions.callouts:
            assert len(callout) <= 25, (
                f"{vertical_id}: callout '{callout}' exceeds 25 chars ({len(callout)})"
            )
