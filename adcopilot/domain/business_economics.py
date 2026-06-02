"""Business-economics inputs for value-based bidding (Phase 5).

Captures the unit economics needed to assign real monetary value to conversions
so the account can move from "count conversions" to value-based bidding (tROAS):
average order value, profit margin, customer LTV, a target ROAS, and a default
lead value for lead-gen. Stored per account.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    updated_at: datetime | None = None

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
