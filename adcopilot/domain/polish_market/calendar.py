"""Polish public holidays and business-hour patterns."""

from __future__ import annotations

from datetime import date


# Fixed-date Polish public holidays (month, day).
# Easter Monday is computed separately — see `get_easter_monday`.
POLISH_FIXED_HOLIDAYS: list[tuple[int, int]] = [
    (1, 1),    # Nowy Rok
    (1, 6),    # Trzech Króli (Epiphany)
    (5, 1),    # Święto Pracy (Labour Day)
    (5, 3),    # Konstytucja 3 Maja (Constitution Day)
    (8, 15),   # Wniebowzięcie NMP (Assumption)
    (11, 1),   # Wszystkich Świętych (All Saints)
    (11, 11),  # Święto Niepodległości (Independence Day)
    (12, 25),  # Boże Narodzenie (Christmas Day 1)
    (12, 26),  # Drugi dzień BN (Christmas Day 2)
]


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm for Easter Sunday."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def get_easter_monday(year: int) -> date:
    """Return Easter Monday for *year*."""
    from datetime import timedelta
    return _easter_sunday(year) + timedelta(days=1)


def get_whit_sunday(year: int) -> date:
    """Return Pentecost (Zielone Świątki) for *year* — 49 days after Easter."""
    from datetime import timedelta
    return _easter_sunday(year) + timedelta(days=49)


def get_corpus_christi(year: int) -> date:
    """Return Corpus Christi (Boże Ciało) — 60 days after Easter."""
    from datetime import timedelta
    return _easter_sunday(year) + timedelta(days=60)


def get_polish_holidays(year: int) -> set[date]:
    """Return all Polish public holidays for *year* as a set of dates."""
    holidays: set[date] = set()
    for month, day in POLISH_FIXED_HOLIDAYS:
        holidays.add(date(year, month, day))
    holidays.add(get_easter_monday(year))
    holidays.add(get_whit_sunday(year))
    holidays.add(get_corpus_christi(year))
    return holidays


def is_polish_holiday(d: date) -> bool:
    """Return True if *d* is a Polish public holiday."""
    return d in get_polish_holidays(d.year)


# ---------------------------------------------------------------------------
# Polish business-hour patterns by vertical
# ---------------------------------------------------------------------------

# Format: (start_hour, end_hour) for weekdays and optional weekend
POLISH_BUSINESS_HOURS: dict[str, dict[str, tuple[int, int] | None]] = {
    "generic":     {"weekday": (8, 17), "saturday": None,       "sunday": None},
    "legal":       {"weekday": (8, 17), "saturday": None,       "sunday": None},
    "medical":     {"weekday": (8, 17), "saturday": (9, 14),    "sunday": None},
    "salon":       {"weekday": (9, 19), "saturday": (9, 17),    "sunday": None},
    "restaurant":  {"weekday": (11, 22), "saturday": (11, 23),  "sunday": (11, 21)},
    "ecommerce":   {"weekday": (0, 24), "saturday": (0, 24),    "sunday": (0, 24)},
    "nieruchomości": {"weekday": (8, 17), "saturday": (9, 14),  "sunday": None},
    "edukacja":    {"weekday": (8, 20), "saturday": (9, 15),    "sunday": None},
    "usługi domowe": {"weekday": (7, 18), "saturday": (8, 14),  "sunday": None},
    "prawnik":     {"weekday": (8, 17), "saturday": None,       "sunday": None},
    "lekarz":      {"weekday": (8, 17), "saturday": (9, 14),    "sunday": None},
}
