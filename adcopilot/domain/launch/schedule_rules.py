"""Ad schedule rules — proactive dayparting applied at campaign creation.

Polish market defaults:
  B2B (legal, medical, generic): Mon-Fri 8:00-17:00
  Salon: Mon-Fri 9:00-19:00, Sat 9:00-17:00
  Restaurant: daily 11:00-22:00 (Sat extended to 23:00)
  Ecommerce: no schedule (24/7)
  MICRO tier always gets Mon-Fri 8:00-17:00 to avoid overnight waste.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.launch.budget_tier import BudgetTier
from adcopilot.domain.polish_market.calendar import POLISH_BUSINESS_HOURS

_WEEKDAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
_ALL_DAYS = _WEEKDAYS + ["SATURDAY", "SUNDAY"]

_B2B_VERTICALS = {"legal", "medical", "generic", "prawnik", "lekarz", "nieruchomości"}
_LOCAL_VERTICALS = {"salon", "restaurant", "restauracja", "usługi domowe"}
_EXTENDED_VERTICALS = {"edukacja"}


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


def _schedule_from_polish_hours(vertical: str) -> list[AdScheduleEntry]:
    """Build schedule from POLISH_BUSINESS_HOURS for a known vertical."""
    hours = POLISH_BUSINESS_HOURS.get(vertical)
    if hours is None:
        return _weekday_schedule(8, 17)

    entries: list[AdScheduleEntry] = []
    wd_start, wd_end = hours["weekday"]  # type: ignore[misc]
    if wd_end == 24:
        # 24/7 — no schedule constraint
        return []
    for day in _WEEKDAYS:
        entries.append(AdScheduleEntry(day, wd_start, 0, wd_end, 0))

    sat = hours.get("saturday")
    if sat:
        entries.append(AdScheduleEntry("SATURDAY", sat[0], 0, sat[1], 0))

    sun = hours.get("sunday")
    if sun:
        entries.append(AdScheduleEntry("SUNDAY", sun[0], 0, sun[1], 0))

    return entries


def get_ad_schedule(vertical: str, tier: BudgetTier) -> list[AdScheduleEntry]:
    """Return ad schedule entries for a vertical and budget tier.

    MICRO tier always gets Mon-Fri 8:00-17:00 to avoid overnight waste.
    Ecommerce: no schedule (24/7).
    All other verticals: Polish business hours from POLISH_BUSINESS_HOURS.
    """
    if vertical in ("ecommerce",):
        return []

    if tier == BudgetTier.MICRO:
        return _weekday_schedule(8, 17)

    # Use Polish vertical hours if available
    if vertical in POLISH_BUSINESS_HOURS:
        return _schedule_from_polish_hours(vertical)

    if vertical in _B2B_VERTICALS:
        return _weekday_schedule(8, 17)

    if vertical in _LOCAL_VERTICALS:
        return _schedule_from_polish_hours("salon")

    # Default
    return _weekday_schedule(8, 17)
