"""Tests for Polish holiday calendar and schedule rules."""

from __future__ import annotations

from datetime import date

import pytest

from adcopilot.domain.polish_market.calendar import (
    POLISH_FIXED_HOLIDAYS,
    POLISH_BUSINESS_HOURS,
    get_easter_monday,
    get_polish_holidays,
    is_polish_holiday,
)
from adcopilot.domain.launch.schedule_rules import AdScheduleEntry, get_ad_schedule
from adcopilot.domain.launch.budget_tier import BudgetTier


# ---------------------------------------------------------------------------
# Calendar tests
# ---------------------------------------------------------------------------


def test_fixed_holidays_count() -> None:
    assert len(POLISH_FIXED_HOLIDAYS) >= 9


def test_new_year_is_holiday() -> None:
    assert is_polish_holiday(date(2026, 1, 1))


def test_labour_day_is_holiday() -> None:
    assert is_polish_holiday(date(2026, 5, 1))


def test_independence_day_is_holiday() -> None:
    assert is_polish_holiday(date(2026, 11, 11))


def test_christmas_day_is_holiday() -> None:
    assert is_polish_holiday(date(2026, 12, 25))
    assert is_polish_holiday(date(2026, 12, 26))


def test_regular_working_day_not_holiday() -> None:
    assert not is_polish_holiday(date(2026, 3, 15))  # random Monday


def test_easter_monday_2026() -> None:
    easter_mon = get_easter_monday(2026)
    assert easter_mon == date(2026, 4, 6)


def test_get_polish_holidays_includes_easter_monday() -> None:
    holidays = get_polish_holidays(2026)
    assert date(2026, 4, 6) in holidays  # Easter Monday 2026


def test_get_polish_holidays_count() -> None:
    holidays = get_polish_holidays(2026)
    assert len(holidays) >= 12  # 9 fixed + Easter Monday + Whit Sunday + Corpus Christi


# ---------------------------------------------------------------------------
# Business hours tests
# ---------------------------------------------------------------------------


def test_business_hours_covers_required_verticals() -> None:
    required = {"generic", "legal", "medical", "salon", "restaurant", "ecommerce"}
    assert required <= set(POLISH_BUSINESS_HOURS.keys())


def test_ecommerce_is_24_7() -> None:
    hours = POLISH_BUSINESS_HOURS["ecommerce"]
    assert hours["weekday"] == (0, 24)
    assert hours["saturday"] == (0, 24)
    assert hours["sunday"] == (0, 24)


def test_generic_default_hours() -> None:
    hours = POLISH_BUSINESS_HOURS["generic"]
    assert hours["weekday"] == (8, 17)
    assert hours["saturday"] is None


def test_salon_includes_saturday() -> None:
    hours = POLISH_BUSINESS_HOURS["salon"]
    assert hours["saturday"] is not None
    assert hours["saturday"][0] >= 9


# ---------------------------------------------------------------------------
# schedule_rules tests
# ---------------------------------------------------------------------------


def test_ecommerce_returns_empty_schedule() -> None:
    schedule = get_ad_schedule("ecommerce", BudgetTier.MID)
    assert schedule == []


def test_micro_tier_always_weekdays_only() -> None:
    schedule = get_ad_schedule("salon", BudgetTier.MICRO)
    days = {e.day_of_week for e in schedule}
    assert "SATURDAY" not in days
    assert "SUNDAY" not in days


def test_legal_weekdays_only() -> None:
    schedule = get_ad_schedule("legal", BudgetTier.MID)
    days = {e.day_of_week for e in schedule}
    assert "SATURDAY" not in days
    assert "SUNDAY" not in days


def test_salon_mid_includes_saturday() -> None:
    schedule = get_ad_schedule("salon", BudgetTier.MID)
    days = {e.day_of_week for e in schedule}
    assert "SATURDAY" in days


def test_legal_start_hour_is_8() -> None:
    schedule = get_ad_schedule("legal", BudgetTier.MID)
    weekday_entries = [e for e in schedule if e.day_of_week == "MONDAY"]
    assert weekday_entries[0].start_hour == 8


def test_micro_tier_start_hour_is_8() -> None:
    schedule = get_ad_schedule("legal", BudgetTier.MICRO)
    assert all(e.start_hour == 8 for e in schedule)


def test_all_entries_are_schedule_entries() -> None:
    schedule = get_ad_schedule("salon", BudgetTier.MID)
    assert all(isinstance(e, AdScheduleEntry) for e in schedule)
