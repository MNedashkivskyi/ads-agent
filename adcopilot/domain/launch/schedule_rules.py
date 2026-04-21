"""Ad schedule rules — proactive dayparting applied at campaign creation.

B2B verticals get Mon–Fri 7:00–19:00 to prevent overnight spend waste.
Local service verticals get extended hours 7:00–22:00 daily.
Ecommerce gets no schedule (24/7 is appropriate).
MICRO tier always gets a schedule to avoid overnight waste.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.launch.budget_tier import BudgetTier

_WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
_ALL_DAYS = _WEEKDAYS + ["SATURDAY", "SUNDAY"]

_B2B_VERTICALS = {"legal", "medical", "generic"}
_LOCAL_VERTICALS = {"salon", "restaurant"}


@dataclass(frozen=True)
class AdScheduleEntry:
    day_of_week: str   # "MONDAY" ... "SUNDAY"
    start_hour: int    # 0–23
    start_minute: int  # 0, 15, 30, 45
    end_hour: int      # 0–23
    end_minute: int    # 0, 15, 30, 45


def _weekday_schedule(start_hour: int, end_hour: int) -> list[AdScheduleEntry]:
    return [
        AdScheduleEntry(day, start_hour, 0, end_hour, 0)
        for day in _WEEKDAYS
    ]


def _allday_schedule(start_hour: int, end_hour: int) -> list[AdScheduleEntry]:
    return [
        AdScheduleEntry(day, start_hour, 0, end_hour, 0)
        for day in _ALL_DAYS
    ]


def get_ad_schedule(vertical: str, tier: BudgetTier) -> list[AdScheduleEntry]:
    """Return ad schedule entries for a vertical and budget tier.

    MICRO tier always gets Mon–Fri business hours to avoid overnight waste.
    B2B verticals (legal, medical, generic): Mon–Fri 7:00–19:00.
    Local verticals (salon, restaurant): daily 7:00–22:00.
    Ecommerce: no schedule (24/7 is appropriate for online shopping).
    """
    if vertical == "ecommerce":
        return []

    if tier == BudgetTier.MICRO:
        # MICRO always restricts to business hours to prevent overnight waste
        return _weekday_schedule(7, 19)

    if vertical in _B2B_VERTICALS:
        return _weekday_schedule(7, 19)

    if vertical in _LOCAL_VERTICALS:
        return _allday_schedule(7, 22)

    # Default for unknown verticals at MID/GROWTH
    return _weekday_schedule(7, 19)
