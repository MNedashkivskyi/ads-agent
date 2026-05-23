"""Budget validation against Polish market benchmarks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from adcopilot.domain.polish_market.cpc_benchmarks import get_benchmark


@dataclass(frozen=True)
class BudgetValidationResult:
    is_low: bool
    vertical: str
    location: str
    entered_budget_pln: Decimal
    min_budget_pln: int | None
    recommended_budget_pln: int | None
    warning_message: str | None


def validate_budget(vertical: str, location: str, budget_pln: Decimal) -> BudgetValidationResult:
    """Check budget against Polish benchmarks. Returns warning if below minimum."""
    benchmark = get_benchmark(vertical, location)
    if benchmark is None:
        return BudgetValidationResult(
            is_low=False,
            vertical=vertical,
            location=location,
            entered_budget_pln=budget_pln,
            min_budget_pln=None,
            recommended_budget_pln=None,
            warning_message=None,
        )

    if budget_pln < benchmark.min_monthly_budget_pln:
        from adcopilot.domain.polish_market.currency import format_pln

        msg = (
            f"⚠️ Twój budżet {format_pln(int(budget_pln))} jest niski dla branży "
            f"{vertical} w {location}. "
            f"Rekomendowany minimum to {format_pln(benchmark.min_monthly_budget_pln)}/mies. "
            f"Kontynuujesz?"
        )
        return BudgetValidationResult(
            is_low=True,
            vertical=vertical,
            location=location,
            entered_budget_pln=budget_pln,
            min_budget_pln=benchmark.min_monthly_budget_pln,
            recommended_budget_pln=benchmark.recommended_monthly_budget_pln,
            warning_message=msg,
        )

    return BudgetValidationResult(
        is_low=False,
        vertical=vertical,
        location=location,
        entered_budget_pln=budget_pln,
        min_budget_pln=benchmark.min_monthly_budget_pln,
        recommended_budget_pln=benchmark.recommended_monthly_budget_pln,
        warning_message=None,
    )
