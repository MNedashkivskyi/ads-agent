"""Unit tests for ad schedule rules (Task 4.2)."""

from adcopilot.domain.launch.budget_tier import BudgetTier
from adcopilot.domain.launch.schedule_rules import get_ad_schedule


def test_ecommerce_returns_no_schedule():
    assert get_ad_schedule("ecommerce", BudgetTier.MID) == []
    assert get_ad_schedule("ecommerce", BudgetTier.GROWTH) == []
    assert get_ad_schedule("ecommerce", BudgetTier.MICRO) == []


def test_micro_tier_always_gets_schedule():
    # Even for ecommerce? No — ecommerce is excluded regardless
    # For other verticals, MICRO always gets a schedule
    for vertical in ("legal", "salon", "restaurant", "medical", "generic"):
        schedule = get_ad_schedule(vertical, BudgetTier.MICRO)
        assert len(schedule) > 0, f"{vertical} MICRO should have a schedule"


def test_b2b_verticals_get_weekday_schedule():
    for vertical in ("legal", "medical", "generic"):
        schedule = get_ad_schedule(vertical, BudgetTier.MID)
        days = {e.day_of_week for e in schedule}
        assert "MONDAY" in days
        assert "FRIDAY" in days
        assert "SATURDAY" not in days
        assert "SUNDAY" not in days


def test_b2b_schedule_hours():
    schedule = get_ad_schedule("legal", BudgetTier.MID)
    for entry in schedule:
        assert entry.start_hour == 7
        assert entry.end_hour == 19


def test_local_verticals_get_all_day_schedule():
    for vertical in ("salon", "restaurant"):
        schedule = get_ad_schedule(vertical, BudgetTier.MID)
        days = {e.day_of_week for e in schedule}
        assert "SATURDAY" in days
        assert "SUNDAY" in days


def test_local_verticals_schedule_hours():
    schedule = get_ad_schedule("salon", BudgetTier.MID)
    for entry in schedule:
        assert entry.start_hour == 7
        assert entry.end_hour == 22


def test_micro_tier_b2b_same_as_mid():
    micro_schedule = get_ad_schedule("legal", BudgetTier.MICRO)
    mid_schedule = get_ad_schedule("legal", BudgetTier.MID)
    assert micro_schedule == mid_schedule


def test_schedule_entry_fields():
    schedule = get_ad_schedule("legal", BudgetTier.GROWTH)
    for entry in schedule:
        assert entry.day_of_week in {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}
        assert 0 <= entry.start_hour <= 23
        assert 0 <= entry.end_hour <= 23
        assert entry.start_minute in {0, 15, 30, 45}
        assert entry.end_minute in {0, 15, 30, 45}
