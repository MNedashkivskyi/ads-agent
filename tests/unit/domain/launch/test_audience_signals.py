import pytest

from adcopilot.domain.launch.audience_signals import VERTICAL_AUDIENCES, get_audience_signals
from adcopilot.domain.launch.budget_tier import BudgetTier


def test_micro_tier_returns_empty_for_all_verticals():
    for vertical in list(VERTICAL_AUDIENCES.keys()) + ["unknown"]:
        assert get_audience_signals(vertical, BudgetTier.MICRO) == []


def test_mid_tier_returns_audiences():
    signals = get_audience_signals("salon", BudgetTier.MID)
    assert len(signals) >= 1
    assert any(s.segment_name == "Beauty & Personal Care" for s in signals)


def test_growth_tier_returns_audiences():
    signals = get_audience_signals("legal", BudgetTier.GROWTH)
    assert len(signals) >= 1
    assert any(s.segment_name == "Legal Services" for s in signals)


def test_unknown_vertical_falls_back_to_generic():
    signals = get_audience_signals("unknown_vertical", BudgetTier.MID)
    assert signals == get_audience_signals("generic", BudgetTier.MID)


@pytest.mark.parametrize(
    "vertical", ["salon", "ecommerce", "restaurant", "legal", "medical", "generic"]
)
def test_all_verticals_have_audiences_for_mid(vertical):
    signals = get_audience_signals(vertical, BudgetTier.MID)
    assert len(signals) >= 1


def test_audience_signal_fields():
    signals = get_audience_signals("ecommerce", BudgetTier.GROWTH)
    for s in signals:
        assert isinstance(s.segment_id, int)
        assert s.segment_name
        assert s.segment_type in ("IN_MARKET", "AFFINITY", "CUSTOM_INTENT")
