"""Business-economics inputs for value-based bidding (Phase 5).

Captures the unit economics needed to assign real monetary value to conversions
so the account can move from "count conversions" to value-based bidding (tROAS):
average order value, profit margin, customer LTV, a target ROAS, and a default
lead value for lead-gen. Stored per account.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BusinessEconomics:
    account_id: str
    avg_order_value: float | None = None
    profit_margin_pct: float | None = None  # 0–100
    customer_ltv: float | None = None
    target_roas: float | None = None  # e.g. 4.0 = 400%
    default_lead_value: float | None = None
    currency_code: str = "PLN"
    # Business context (onboarding): goal, target CPA, capacity, brand/exclusions.
    primary_goal: str | None = None  # LEADS | SALES | AWARENESS | CALLS
    target_cpa: float | None = None  # acceptable cost per conversion, currency units
    monthly_conversion_capacity: int | None = None  # how many conversions/mo they can handle
    brand_terms: list[str] = field(default_factory=list)
    excluded_terms: list[str] = field(default_factory=list)
    updated_at: datetime | None = None

    def is_context_configured(self) -> bool:
        """True once the user has supplied a goal or a target — enough to anchor on."""
        return bool(self.primary_goal) or self.target_cpa is not None or self.target_roas is not None

    def is_configured(self) -> bool:
        """True once the user has supplied at least one value input we can bid on."""
        return any(
            v is not None and v > 0
            for v in (
                self.avg_order_value,
                self.customer_ltv,
                self.default_lead_value,
            )
        )
