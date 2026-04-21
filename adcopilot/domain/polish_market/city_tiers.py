"""Polish city tier classification (1=major, 2=regional, 3=rest)."""

from __future__ import annotations

_TIER_1 = {"warszawa", "krakow", "kraków", "wroclaw", "wrocław"}
_TIER_2 = {
    "gdansk", "gdańsk", "poznan", "poznań", "lodz", "łódź",
    "katowice", "szczecin", "bydgoszcz", "lublin",
}


def classify_city(city: str) -> int:
    """Return tier 1, 2, or 3 for a Polish city name."""
    normalized = city.strip().lower()
    if normalized in _TIER_1:
        return 1
    if normalized in _TIER_2:
        return 2
    return 3
