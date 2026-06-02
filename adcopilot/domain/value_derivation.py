"""Derive a conversion value from business economics (Phase 5).

Turns unit economics into the monetary value to send with a conversion so
Smart Bidding can optimize for value (tROAS) rather than raw conversion count.
"""

from __future__ import annotations

from adcopilot.domain.business_economics import BusinessEconomics

# Categories representing a sale (value from order economics) vs a lead.
_PURCHASE_CATEGORIES = {"PURCHASE", "ADD_TO_CART", "BEGIN_CHECKOUT", "SUBSCRIBE_PAID", "STORE_SALE"}


def derive_conversion_value(econ: BusinessEconomics, *, category: str) -> float | None:
    """Best-fit value for a conversion of the given category, or None if unknown.

    - Purchases: average order value × profit margin (or AOV if no margin set).
    - Leads: explicit default lead value, else customer LTV.
    """
    if category in _PURCHASE_CATEGORIES:
        if econ.avg_order_value and econ.avg_order_value > 0:
            if econ.profit_margin_pct and econ.profit_margin_pct > 0:
                return round(econ.avg_order_value * econ.profit_margin_pct / 100.0, 2)
            return float(econ.avg_order_value)
        return None
    # Lead-gen categories.
    if econ.default_lead_value and econ.default_lead_value > 0:
        return float(econ.default_lead_value)
    if econ.customer_ltv and econ.customer_ltv > 0:
        return float(econ.customer_ltv)
    return None
