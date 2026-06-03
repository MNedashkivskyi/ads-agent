"""Per-account spend-safety configuration (spend-safety system).

Caps are opt-in: a `None` cap means "no limit" and the guardrail/breach checks
treat it as not-applicable (no behaviour change until the user sets a value).
`auto_pause_enabled` gates whether a real spend-cap breach may trigger an
automatic pause — off by default (human-in-the-loop).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class SpendSafetyConfigError(ValueError):
    """Raised when a spend-safety config is invalid."""


@dataclass
class SpendSafetyConfig:
    account_id: str
    monthly_spend_cap_micros: int | None = None
    daily_spend_cap_micros: int | None = None
    per_campaign_daily_cap_micros: int | None = None
    max_budget_increase_pct: float = 50.0  # cap on a single budget-raise action
    warning_threshold_pct: float = 80.0  # % of a cap at which to warn
    auto_pause_enabled: bool = False
    currency_code: str = "PLN"
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "monthly_spend_cap_micros",
            "daily_spend_cap_micros",
            "per_campaign_daily_cap_micros",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise SpendSafetyConfigError(f"{name} must be non-negative")
        if not (0 < self.max_budget_increase_pct <= 1000):
            raise SpendSafetyConfigError("max_budget_increase_pct must be in (0, 1000]")
        if not (0 <= self.warning_threshold_pct <= 100):
            raise SpendSafetyConfigError("warning_threshold_pct must be in [0, 100]")

    def is_configured(self) -> bool:
        """True if the user has set any cap (so the system has something to enforce)."""
        return any(
            v is not None
            for v in (
                self.monthly_spend_cap_micros,
                self.daily_spend_cap_micros,
                self.per_campaign_daily_cap_micros,
            )
        )
