"""Ad schedule rules — proactive dayparting applied at campaign creation.

Polish market defaults:
  B2B (legal, medical, generic): Mon-Fri 7:00-19:00
  Local (salon, restaurant): all 7 days 7:00-22:00
  Ecommerce: no schedule (24/7)
  MICRO tier always gets the same schedule as MID to avoid overnight waste.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.launch.budget_tier import BudgetTier

_WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
_ALL_DAYS = _WEEKDAYS + ["SATURDAY", "SUNDAY"]

_B2B_VERTICALS = {"legal", "medical", "generic", "prawnik", "lekarz", "nieruchomości"}
_LOCAL_VERTICALS = {"salon", "restaurant", "restauracja", "usługi domowe"}


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

    Ecommerce: no schedule (24/7).
    B2B verticals: Mon-Fri 7:00-19:00.
    Local verticals: all 7 days 7:00-22:00.
    """
    if vertical in ("ecommerce",):
        return []

    if vertical in _B2B_VERTICALS:
        return _weekday_schedule(7, 19)

    if vertical in _LOCAL_VERTICALS:
        return _allday_schedule(7, 22)

    # Default (covers MICRO tier and unknown verticals)
    return _weekday_schedule(7, 19)
