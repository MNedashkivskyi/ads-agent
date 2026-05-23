"""PLN currency formatting utilities for Polish market user-facing text."""

from __future__ import annotations

from decimal import Decimal

# Non-breaking space (U+00A0) as thousands separator per Polish convention
_NBSP = "\u00a0"


def format_pln(amount: float | int | Decimal) -> str:
    """Format a PLN monetary amount using Polish convention.

    Output:
      - "1 234,56 zł"  (non-breaking space as thousands separator, comma decimal)
      - "1 234 zł"     for round amounts

    Edge cases: 0 → "0 zł", negative → "-1 234,56 zł"
    """
    value = float(amount)
    negative = value < 0
    abs_value = abs(value)

    # Determine if we need grosze (cents)
    rounded = round(abs_value, 2)
    cents = round((rounded % 1) * 100)
    whole = int(rounded)

    # Format thousands with non-breaking spaces
    whole_str = f"{whole:,}".replace(",", _NBSP)

    formatted = f"{whole_str} zł" if cents == 0 else f"{whole_str},{cents:02d} zł"

    return f"-{formatted}" if negative else formatted


def format_pln_micros(micros: int) -> str:
    """Format Google Ads micros (PLN) to Polish currency string."""
    return format_pln(micros / 1_000_000)
