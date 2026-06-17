"""Infer a Polish-market vertical from an account's campaign/keyword text (T-followup).

The free audit has no declared vertical, so without one the engine stays
conservative (no benchmark -> only junk-intent waste counts). This lightweight,
dependency-free classifier guesses the vertical from the words already in the
account's campaign names and keywords, unlocking the benchmark-anchored tiers
(egregious zero-conversion spend + Quality-Score overpayment) for a stronger,
still-defensible headline. Returns None when there is no clear signal — we never
guess a vertical we aren't reasonably sure of.

Verticals match ``domain/polish_market/cpc_benchmarks``.
"""

from __future__ import annotations

from collections.abc import Iterable

_VERTICAL_SIGNALS: dict[str, tuple[str, ...]] = {
    "salon": ("fryzjer", "salon", "paznokcie", "manicure", "kosmetyk", "barber", "uroda", "spa"),
    "restauracja": (
        "restauracja",
        "pizza",
        "catering",
        "kawiarnia",
        "bistro",
        "menu",
        "dowóz jedzenia",
    ),
    "prawnik": ("prawnik", "adwokat", "kancelaria", "radca prawny", "porada prawna", "rozwód"),
    "lekarz": ("klinika", "dentysta", "stomatolog", "przychodnia", "ortodonta", "gabinet lekarski"),
    "e-commerce": ("sklep", "kup online", "wysyłka", "promocja", "koszyk", "e-commerce", "outlet"),
    "nieruchomości": (
        "nieruchomości",
        "mieszkanie",
        "deweloper",
        "działka",
        "wynajem",
        "na sprzedaż",
    ),
    "edukacja": ("kurs", "szkolenie", "korepetycje", "szkoła językowa", "studia", "lekcje"),
    "usługi domowe": (
        "hydraulik",
        "elektryk",
        "remont",
        "sprzątanie",
        "malowanie",
        "klimatyzacja",
    ),
}


def infer_vertical(texts: Iterable[str]) -> str | None:
    """Best-guess vertical from campaign names + keyword texts, or None if unclear."""
    blob = " ".join(t.lower() for t in texts if t)
    if not blob.strip():
        return None
    scores = {
        vertical: sum(blob.count(signal) for signal in signals)
        for vertical, signals in _VERTICAL_SIGNALS.items()
    }
    best = max(scores, key=lambda v: scores[v])
    return best if scores[best] > 0 else None
