"""Preventive spend guardrail (spend-safety system).

Validates the agent's OWN spend-increasing mutations against per-account caps
*before* they execute — making CLAUDE.md's "budget tier integrity, no bypass" real.

Pure and fully testable. The guard is **inert until the user opts in** (sets at
least one cap, `SpendSafetyConfig.is_configured()`), so existing accounts see no
behaviour change. It covers single-campaign spend *raises* with a numeric delta:
budget increases (`INCREASE_BUDGET`/`ADJUST_BUDGET`) and target-CPA relaxation
(`RELAX_TARGET_CPA`/`SET_TARGET_CPA`). Reallocation is net-zero at the account
level and bidding-strategy switches carry no numeric delta — those are covered by
the reactive breach detector on realized spend, not here.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.spend_safety import SpendSafetyConfig

BUDGET_KINDS = {"INCREASE_BUDGET", "ADJUST_BUDGET"}
TCPA_KINDS = {"RELAX_TARGET_CPA", "SET_TARGET_CPA"}


@dataclass
class SpendAction:
    """A proposed spend-changing mutation, normalized for the guard."""

    kind: str
    campaign_id: int | None = None
    current_budget_micros: int | None = None
    new_budget_micros: int | None = None
    current_target_cpa_micros: int | None = None
    new_target_cpa_micros: int | None = None


@dataclass
class AccountSpendContext:
    """Current account spend, used for pace-aware cap projection."""

    month_to_date_spend_micros: int = 0
    today_spend_micros: int = 0
    days_elapsed: int = 1  # days into the current month incl. today (>=1)
    days_in_month: int = 30


@dataclass
class GuardDecision:
    allowed: bool
    code: str  # OK | MAX_BUDGET_INCREASE | CAMPAIGN_DAILY_CAP | DAILY_CAP | MONTHLY_CAP | TCPA_RELAX
    reason_pl: str = ""


_ALLOW = GuardDecision(allowed=True, code="OK")


def _pln(micros: int | float) -> str:
    return f"{micros / 1_000_000:.2f} PLN"


def evaluate_spend_action(
    action: SpendAction,
    config: SpendSafetyConfig,
    ctx: AccountSpendContext,
) -> GuardDecision:
    """Allow or deny a proposed spend-increasing action against the account's caps."""
    if not config.is_configured():
        return _ALLOW

    if action.kind in TCPA_KINDS:
        return _evaluate_tcpa(action, config)
    if action.kind in BUDGET_KINDS:
        return _evaluate_budget(action, config, ctx)
    # Out of the guard's numeric scope (reallocation, strategy switch).
    return _ALLOW


def _evaluate_tcpa(action: SpendAction, config: SpendSafetyConfig) -> GuardDecision:
    current = action.current_target_cpa_micros
    new = action.new_target_cpa_micros
    if not current or new is None or new <= current:
        return _ALLOW  # tightening or unknown baseline never raises spend
    increase_pct = (new - current) / current * 100
    if increase_pct > config.max_budget_increase_pct:
        return GuardDecision(
            allowed=False,
            code="TCPA_RELAX",
            reason_pl=(
                f"Rozluźnienie docelowego CPA o {increase_pct:.0f}% przekracza dozwolony "
                f"limit {config.max_budget_increase_pct:.0f}% na jedną zmianę "
                f"({_pln(current)} → {_pln(new)})."
            ),
        )
    return _ALLOW


def _evaluate_budget(
    action: SpendAction, config: SpendSafetyConfig, ctx: AccountSpendContext
) -> GuardDecision:
    new = action.new_budget_micros
    current = action.current_budget_micros
    if new is None:
        return _ALLOW
    delta = new - (current or 0)

    # Per-campaign daily cap applies regardless of direction.
    if (
        config.per_campaign_daily_cap_micros is not None
        and new > config.per_campaign_daily_cap_micros
    ):
        return GuardDecision(
            allowed=False,
            code="CAMPAIGN_DAILY_CAP",
            reason_pl=(
                f"Budżet kampanii {_pln(new)} przekracza dzienny limit na kampanię "
                f"{_pln(config.per_campaign_daily_cap_micros)}."
            ),
        )

    if delta <= 0:
        return _ALLOW  # a reduction never breaches a spend cap

    # Single-action raise cap.
    if current and current > 0:
        increase_pct = delta / current * 100
        if increase_pct > config.max_budget_increase_pct:
            return GuardDecision(
                allowed=False,
                code="MAX_BUDGET_INCREASE",
                reason_pl=(
                    f"Podwyżka budżetu o {increase_pct:.0f}% przekracza dozwolony limit "
                    f"{config.max_budget_increase_pct:.0f}% na jedną zmianę "
                    f"({_pln(current)} → {_pln(new)})."
                ),
            )

    # Account daily cap: today's spend + the extra daily budget.
    if config.daily_spend_cap_micros is not None:
        projected_today = ctx.today_spend_micros + delta
        if projected_today > config.daily_spend_cap_micros:
            return GuardDecision(
                allowed=False,
                code="DAILY_CAP",
                reason_pl=(
                    f"Po tej zmianie dzienne wydatki konta ({_pln(projected_today)}) "
                    f"przekroczą dzienny limit {_pln(config.daily_spend_cap_micros)}."
                ),
            )

    # Account monthly cap: pace-aware end-of-month projection + the raise's effect
    # over the remaining days of the month.
    if config.monthly_spend_cap_micros is not None:
        days_elapsed = max(1, ctx.days_elapsed)
        remaining_days = max(0, ctx.days_in_month - days_elapsed)
        run_rate = ctx.month_to_date_spend_micros / days_elapsed
        projected = ctx.month_to_date_spend_micros + run_rate * remaining_days
        projected_after = projected + delta * remaining_days
        if projected_after > config.monthly_spend_cap_micros:
            return GuardDecision(
                allowed=False,
                code="MONTHLY_CAP",
                reason_pl=(
                    f"Prognozowane wydatki konta na koniec miesiąca ({_pln(projected_after)}) "
                    f"przekroczą miesięczny limit {_pln(config.monthly_spend_cap_micros)}."
                ),
            )

    return _ALLOW
