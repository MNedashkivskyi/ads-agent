"""Map each audit waste category to the concrete fix we apply (Audit Funnel T2.5).

Turns a diagnostic finding ("you're wasting X on junk search terms") into the
named action the product takes ("add negative keywords") — so the reveal can show
*how* each finding gets fixed, and the app can deep-link a finding to the matching,
applyable recommendations. Pure data + lookup: no DB, no Google Ads.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.audit import WasteCategory
from adcopilot.domain.recommendation import RecommendationKind


@dataclass(frozen=True)
class FixAction:
    """The fix for a waste category: the recommendation kind, a Polish label, and
    whether we apply it automatically (one-click) vs. it being advisory."""

    kind: RecommendationKind
    label_pl: str
    actionable: bool


# One canonical fix per waste category. ``actionable`` mirrors whether the kind has
# an automatic executor (one-click apply) vs. an advisory action the user completes.
# WasteCategory.ISSUE is intentionally absent — it's a generic, context-free flag.
_FIXES: dict[WasteCategory, FixAction] = {
    WasteCategory.SEARCHTERM_WASTE: FixAction(
        RecommendationKind.ADD_NEGATIVE_KEYWORD,
        "Dodajemy wykluczające słowa kluczowe, aby odciąć ten ruch",
        True,
    ),
    WasteCategory.NEGATIVE_BLOCKABLE: FixAction(
        RecommendationKind.ADD_NEGATIVE_KEYWORD,
        "Dodajemy wykluczające słowa kluczowe, aby odciąć ten ruch",
        True,
    ),
    WasteCategory.KEYWORD_WASTE: FixAction(
        RecommendationKind.PAUSE_KEYWORD,
        "Wstrzymujemy słowa kluczowe, które nie przynoszą konwersji",
        True,
    ),
    WasteCategory.QS_OVERPAYMENT: FixAction(
        RecommendationKind.IMPROVE_QUALITY_SCORE,
        "Poprawiamy Wynik Jakości, aby obniżyć stawki za kliknięcie",
        False,
    ),
    WasteCategory.MEASUREMENT_GAP: FixAction(
        RecommendationKind.ENABLE_CONVERSION_TRACKING,
        "Włączamy śledzenie konwersji, aby przestać optymalizować na ślepo",
        False,
    ),
}


def fix_action_for(category: WasteCategory) -> FixAction | None:
    """The canonical fix for a waste category, or None (e.g. the generic ISSUE)."""
    return _FIXES.get(category)
