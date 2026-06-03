from __future__ import annotations

from adcopilot.domain.spend_breach import (
    CampaignSpend,
    decide_escalation,
    detect_spend_cap_breaches,
)
from adcopilot.domain.spend_safety import SpendSafetyConfig


def _detect(config, **kw):
    base = dict(
        account_mtd_spend_micros=0,
        account_today_spend_micros=0,
        days_elapsed=15,
        days_in_month=30,
        campaign_spend=None,
    )
    base.update(kw)
    return detect_spend_cap_breaches(config, **base)


def test_no_breaches_when_not_configured() -> None:
    assert _detect(SpendSafetyConfig(account_id="a"), account_today_spend_micros=10**12) == []


def test_account_daily_breach() -> None:
    cfg = SpendSafetyConfig(account_id="a", daily_spend_cap_micros=100_000_000)
    breaches = _detect(cfg, account_today_spend_micros=120_000_000)
    assert len(breaches) == 1
    assert breaches[0].cap_type == "DAILY"
    assert breaches[0].is_breach is True


def test_account_daily_warning() -> None:
    cfg = SpendSafetyConfig(account_id="a", daily_spend_cap_micros=100_000_000, warning_threshold_pct=80)
    breaches = _detect(cfg, account_today_spend_micros=85_000_000)
    assert breaches[0].severity == "WARNING"


def test_monthly_breach_when_mtd_exceeds_cap() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1_000_000_000)
    breaches = _detect(cfg, account_mtd_spend_micros=1_100_000_000, days_elapsed=20)
    assert breaches[0].cap_type == "MONTHLY"
    assert breaches[0].is_breach is True


def test_monthly_warning_when_projected_exceeds_cap() -> None:
    cfg = SpendSafetyConfig(account_id="a", monthly_spend_cap_micros=1_000_000_000)
    # MTD 600 at day 15/30 -> projected 1200 > 1000 cap, but MTD < cap -> WARNING
    breaches = _detect(cfg, account_mtd_spend_micros=600_000_000, days_elapsed=15)
    assert breaches[0].cap_type == "MONTHLY"
    assert breaches[0].severity == "WARNING"


def test_per_campaign_daily_breach_identifies_campaign() -> None:
    cfg = SpendSafetyConfig(account_id="a", per_campaign_daily_cap_micros=50_000_000)
    breaches = _detect(
        cfg,
        campaign_spend=[CampaignSpend(1, 10_000_000), CampaignSpend(2, 70_000_000)],
    )
    assert len(breaches) == 1
    assert breaches[0].campaign_id == 2
    assert breaches[0].scope == "campaign"


# --- escalation routing ---

def _campaign_breach() -> "object":
    cfg = SpendSafetyConfig(account_id="a", per_campaign_daily_cap_micros=10)
    return detect_spend_cap_breaches(
        cfg, account_mtd_spend_micros=0, account_today_spend_micros=0,
        days_elapsed=1, days_in_month=30, campaign_spend=[CampaignSpend(5, 100)],
    )[0]


def test_escalation_auto_pause_campaign_when_enabled() -> None:
    cfg = SpendSafetyConfig(account_id="a", per_campaign_daily_cap_micros=10, auto_pause_enabled=True)
    action = decide_escalation(_campaign_breach(), cfg)
    assert action.action == "AUTO_PAUSE_CAMPAIGN"
    assert action.campaign_id == 5


def test_escalation_recommend_when_not_enabled() -> None:
    cfg = SpendSafetyConfig(account_id="a", per_campaign_daily_cap_micros=10, auto_pause_enabled=False)
    action = decide_escalation(_campaign_breach(), cfg)
    assert action.action == "RECOMMEND_PAUSE"
    assert action.campaign_id == 5


def test_escalation_account_breach_auto_panic() -> None:
    cfg = SpendSafetyConfig(account_id="a", daily_spend_cap_micros=10, auto_pause_enabled=True)
    breach = detect_spend_cap_breaches(
        cfg, account_mtd_spend_micros=0, account_today_spend_micros=100,
        days_elapsed=1, days_in_month=30,
    )[0]
    assert decide_escalation(breach, cfg).action == "AUTO_PANIC_PAUSE_ACCOUNT"


def test_escalation_warning_is_notify_only() -> None:
    cfg = SpendSafetyConfig(account_id="a", daily_spend_cap_micros=100, warning_threshold_pct=80, auto_pause_enabled=True)
    breach = detect_spend_cap_breaches(
        cfg, account_mtd_spend_micros=0, account_today_spend_micros=85,
        days_elapsed=1, days_in_month=30,
    )[0]
    assert breach.severity == "WARNING"
    assert decide_escalation(breach, cfg).action == "NOTIFY_ONLY"
