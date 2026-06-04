"""Reactive spend-cap breach detection + escalation policy (spend-safety system).

Pure and fully testable. Given current realized spend and the account's
`SpendSafetyConfig`, `detect_spend_cap_breaches` returns the breaches (account
monthly, account daily, per-campaign daily) graded WARNING (>= warning threshold)
or BREACH (>= cap). `decide_escalation` maps a BREACH to a protective action,
honoring the notify-default / auto-pause-opt-in policy.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.spend_safety import SpendSafetyConfig

WARNING = "WARNING"
BREACH = "BREACH"


@dataclass
class CampaignSpend:
    campaign_id: int
    today_spend_micros: int


@dataclass
class SpendBreach:
    cap_type: str  # MONTHLY | DAILY | CAMPAIGN_DAILY
    scope: str  # account | campaign
    severity: str  # WARNING | BREACH
    current_micros: int
    cap_micros: int
    campaign_id: int | None = None

    @property
    def is_breach(self) -> bool:
        return self.severity == BREACH


def _grade(current: float, cap: int, warning_pct: float) -> str | None:
    if current >= cap:
        return BREACH
    if current >= cap * (warning_pct / 100.0):
        return WARNING
    return None


def detect_spend_cap_breaches(
    config: SpendSafetyConfig,
    *,
    account_mtd_spend_micros: int,
    account_today_spend_micros: int,
    days_elapsed: int,
    days_in_month: int,
    campaign_spend: list[CampaignSpend] | None = None,
) -> list[SpendBreach]:
    """Return graded breaches of the account's configured caps (empty if none/opt-out)."""
    if not config.is_configured():
        return []
    breaches: list[SpendBreach] = []

    # Account monthly cap — pace-aware: a BREACH is real-or-projected overrun.
    if config.monthly_spend_cap_micros is not None:
        cap = config.monthly_spend_cap_micros
        days_elapsed = max(1, days_elapsed)
        projected = account_mtd_spend_micros / days_elapsed * days_in_month
        if account_mtd_spend_micros >= cap or projected >= cap:
            severity = BREACH if account_mtd_spend_micros >= cap else WARNING
            breaches.append(
                SpendBreach(
                    cap_type="MONTHLY",
                    scope="account",
                    severity=severity,
                    current_micros=int(account_mtd_spend_micros),
                    cap_micros=cap,
                )
            )
        elif (g := _grade(account_mtd_spend_micros, cap, config.warning_threshold_pct)):
            breaches.append(
                SpendBreach("MONTHLY", "account", g, int(account_mtd_spend_micros), cap)
            )

    # Account daily cap.
    if config.daily_spend_cap_micros is not None:
        g = _grade(account_today_spend_micros, config.daily_spend_cap_micros, config.warning_threshold_pct)
        if g:
            breaches.append(
                SpendBreach(
                    "DAILY", "account", g, int(account_today_spend_micros), config.daily_spend_cap_micros
                )
            )

    # Per-campaign daily cap.
    if config.per_campaign_daily_cap_micros is not None and campaign_spend:
        cap = config.per_campaign_daily_cap_micros
        for cs in campaign_spend:
            g = _grade(cs.today_spend_micros, cap, config.warning_threshold_pct)
            if g:
                breaches.append(
                    SpendBreach("CAMPAIGN_DAILY", "campaign", g, cs.today_spend_micros, cap, cs.campaign_id)
                )

    return breaches


@dataclass
class EscalationAction:
    action: str  # NOTIFY_ONLY | RECOMMEND_PAUSE | AUTO_PAUSE_CAMPAIGN | AUTO_PANIC_PAUSE_ACCOUNT
    campaign_id: int | None = None


def decide_escalation(breach: SpendBreach, config: SpendSafetyConfig) -> EscalationAction:
    """Map a breach to a protective action. Always notify; pause only on BREACH.

    Auto-pause is strictly opt-in. Without it, a BREACH yields a human-approved
    pause proposal (campaign scope) or a notification (account scope).
    """
    if not breach.is_breach:
        return EscalationAction("NOTIFY_ONLY")

    if config.auto_pause_enabled:
        if breach.scope == "campaign" and breach.campaign_id is not None:
            return EscalationAction("AUTO_PAUSE_CAMPAIGN", campaign_id=breach.campaign_id)
        return EscalationAction("AUTO_PANIC_PAUSE_ACCOUNT")

    if breach.scope == "campaign" and breach.campaign_id is not None:
        return EscalationAction("RECOMMEND_PAUSE", campaign_id=breach.campaign_id)
    return EscalationAction("NOTIFY_ONLY")
