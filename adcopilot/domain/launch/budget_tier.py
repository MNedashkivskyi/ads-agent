"""Budget tier classification for campaign-launch decisions.

The tier determines bidding strategy, campaign structure, ad extension
generation, audience signals, and brand campaign separation downstream.

Thresholds are expressed in PLN (Polish Zloty) per month.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class BudgetTier(StrEnum):
    MICRO = "micro"   # 100–499 PLN/mo (~$25–$125)
    MID = "mid"       # 500–2,999 PLN/mo (~$125–$750)
    GROWTH = "growth" # 3,000–20,000 PLN/mo (~$750–$5,000)


# Thresholds in PLN
_MID_THRESHOLD = Decimal("500")
_GROWTH_THRESHOLD = Decimal("3000")


def classify_budget_tier(monthly_budget_pln: Decimal) -> BudgetTier:
    """Classify a monthly PLN budget into a :class:`BudgetTier`.

    Args:
        monthly_budget_pln: Monthly advertising budget in PLN as a Decimal.

    Returns:
        The appropriate :class:`BudgetTier` for the given budget.
    """
    if monthly_budget_pln >= _GROWTH_THRESHOLD:
        return BudgetTier.GROWTH
    if monthly_budget_pln >= _MID_THRESHOLD:
        return BudgetTier.MID
    return BudgetTier.MICRO
