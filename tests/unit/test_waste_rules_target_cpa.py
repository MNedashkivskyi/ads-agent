"""BC4: waste rules anchor to the client's target CPA when configured."""

from __future__ import annotations

from adcopilot.application.detection.rules.rule_01_wasted_search_term import WastedSearchTermRule
from adcopilot.application.detection.rules.rule_02_zero_conversion_keyword import (
    ZeroConversionKeywordRule,
)
from adcopilot.domain.business_economics import BusinessEconomics
from tests.unit.test_detection_rules import _ctx, _keyword, _search_term


def test_rule02_uses_target_cpa_when_set() -> None:
    # cost 10M: below 2× historical avg (20M) but ≥ target CPA (8M).
    kw = _keyword(criterion_id=1, ad_group_id=10, clicks=30, conversions=0.0, cost_micros=10_000_000)
    rule = ZeroConversionKeywordRule()

    # No economics -> falls back to 2× avg (20M) -> not flagged.
    assert rule.detect(_ctx(keywords=[kw])) == []

    # Target CPA = 8 -> threshold 8M -> flagged.
    econ = BusinessEconomics(account_id="a", target_cpa=8.0)
    recs = rule.detect(_ctx(keywords=[kw], business_economics=econ))
    assert len(recs) == 1
    assert recs[0].evidence["threshold_basis"] == "target_cpa"


def test_rule01_uses_target_cpa_floor_when_set() -> None:
    st = _search_term(ad_group_id=10, search_term="free shipping", clicks=5, conversions=0.0, cost_micros=2_500_000)
    rule = WastedSearchTermRule()

    # No economics -> threshold = 30% of avg (10M) = 3M -> 2.5M not flagged.
    assert rule.detect(_ctx(search_terms=[st])) == []

    # Target CPA = 5 -> threshold = 30% of 5M = 1.5M -> 2.5M flagged.
    econ = BusinessEconomics(account_id="a", target_cpa=5.0)
    recs = rule.detect(_ctx(search_terms=[st], business_economics=econ))
    assert len(recs) == 1
