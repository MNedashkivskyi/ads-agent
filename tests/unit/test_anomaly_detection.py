"""Unit tests for AnomalyDetectionUseCase — all 5 anomaly types.

Strategy
--------
All Google Ads I/O is replaced by ``FakeHourlyMetrics`` which returns
synthetic baseline / current data.  All persistence goes through
``InMemoryAlertRepository``.  No database or network calls.

Test matrix
-----------
1. Spend spike — current > 2x baseline -> SPEND_SPIKE alert
2. Spend normal — current <= 2x baseline -> no alert
3. Conversion drought — 6 consecutive zero-conversion hours (baseline >0) -> alert
4. Conversion drought — fewer than 6 zero hours -> no alert
5. Conversion drought — baseline is also 0 -> no alert (no expected conversions)
6. Budget burning fast — >80% consumed before 14:00 UTC -> alert
7. Budget fine — >80% but after 14:00 UTC -> no alert (normal)
8. Budget fine — <=80% before 14:00 UTC -> no alert
9. Tracking error — has_errors=True -> alert
10. Tracking ok — has_errors=False -> no alert
11. Impression share drop — WoW < -30 pp -> alert
12. Impression share small drop — WoW > -30 pp -> no alert
13. Impression share unavailable — None → no alert
14. Rate limit — 3 alerts already in 24h → subsequent anomalies suppressed
15. Rate limit — partial quota remaining → only remaining slots filled
16. All 5 anomalies at once — 3 alerts created, 2 suppressed
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from adcopilot.application.anomaly.anomaly_detection_use_case import (
    _MAX_ALERTS_PER_DAY,
    _SPEND_SPIKE_MULTIPLIER,
    _ZERO_CONVERSION_HOURS,
    AnomalyDetectionUseCase,
)
from adcopilot.application.ports.hourly_metrics import (
    ConversionTrackingStatus,
    DailyBudgetStatus,
    HourlyMetric,
)
from adcopilot.domain.alert import Alert, AlertKind, AlertStatus
from adcopilot.domain.entities import AccountId

# ── Helpers ──────────────────────────────────────────────────────────────────

_ACCOUNT_ID = AccountId("00000000-0000-0000-0000-000000000001")
_CUSTOMER_ID = "123-456-7890"
_REFRESH_TOKEN = "fake-refresh-token"

# Baseline reference time: 08:00 UTC (before 14:00 → budget checks active)
_NOW_MORNING = datetime(2026, 4, 16, 8, 0, 0, tzinfo=UTC)
# Reference time: 15:00 UTC (after 14:00 → budget checks skip)
_NOW_AFTERNOON = datetime(2026, 4, 16, 15, 0, 0, tzinfo=UTC)


def _metric(
    hour: int = 8,
    spend_micros: int = 1_000_000,
    conversions: float = 5.0,
    impressions: int = 1000,
    impression_share: float | None = 0.5,
    date: str = "2026-04-16",
) -> HourlyMetric:
    return HourlyMetric(
        date=date,
        hour=hour,
        spend_micros=spend_micros,
        conversions=conversions,
        impressions=impressions,
        impression_share=impression_share,
    )


# ── In-memory fakes ──────────────────────────────────────────────────────────


class InMemoryAlertRepository:
    def __init__(self, existing_count: int = 0) -> None:
        self.saved: list[Alert] = []
        self._existing_count = existing_count

    async def save(self, alert: Alert) -> None:
        self.saved.append(alert)

    async def count_since(self, account_id: AccountId, since: datetime) -> int:
        return self._existing_count

    async def get_open(self, account_id: AccountId, kind: AlertKind) -> Alert | None:
        for a in reversed(self.saved):
            if a.kind == kind and a.status == AlertStatus.OPEN:
                return a
        return None

    async def is_kind_suppressed(
        self, account_id: AccountId, kind: AlertKind, now: datetime
    ) -> bool:
        return False  # no user-ack suppression in unit tests


class FakeHourlyMetrics:
    """Configurable stub for HourlyMetricsPort."""

    def __init__(
        self,
        last_hours: list[HourlyMetric] | None = None,
        baseline: HourlyMetric | None = None,
        budget_statuses: list[DailyBudgetStatus] | None = None,
        tracking_status: ConversionTrackingStatus | None = None,
        is_wow: float | None = None,
    ) -> None:
        self._last_hours = last_hours or []
        self._baseline = baseline
        self._budget_statuses = budget_statuses or []
        self._tracking_status = tracking_status or ConversionTrackingStatus(
            has_errors=False, error_detail=None
        )
        self._is_wow = is_wow

    async def get_last_n_hours(
        self,
        account_id: Any,
        customer_id: Any,
        refresh_token: Any,
        n: int,
    ) -> list[HourlyMetric]:
        return self._last_hours[-n:]

    async def get_baseline_for_hour(
        self,
        account_id: Any,
        customer_id: Any,
        refresh_token: Any,
        hour_of_day: int,
        day_of_week: int,
        lookback_days: int = 7,
    ) -> HourlyMetric | None:
        return self._baseline

    async def get_daily_budget_status(
        self,
        account_id: Any,
        customer_id: Any,
        refresh_token: Any,
    ) -> list[DailyBudgetStatus]:
        return self._budget_statuses

    async def get_conversion_tracking_status(
        self,
        account_id: Any,
        customer_id: Any,
        refresh_token: Any,
    ) -> ConversionTrackingStatus:
        return self._tracking_status

    async def get_impression_share_wow(
        self,
        account_id: Any,
        customer_id: Any,
        refresh_token: Any,
    ) -> float | None:
        return self._is_wow


def _make_uc(
    metrics: FakeHourlyMetrics,
    existing_alerts: int = 0,
) -> tuple[AnomalyDetectionUseCase, InMemoryAlertRepository]:
    repo = InMemoryAlertRepository(existing_count=existing_alerts)
    uc = AnomalyDetectionUseCase(metrics=metrics, alert_repo=repo)
    return uc, repo


# ── Test 1: Spend spike ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spend_spike_triggers_alert() -> None:
    """Current spend > 2x baseline -> SPEND_SPIKE alert created."""
    baseline_spend = 1_000_000  # 1 PLN
    current_spend = int(baseline_spend * (_SPEND_SPIKE_MULTIPLIER + 0.5))  # 2.5x -> spike

    metrics = FakeHourlyMetrics(
        last_hours=[_metric(spend_micros=current_spend)],
        baseline=_metric(spend_micros=baseline_spend),
    )
    uc, repo = _make_uc(metrics)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    assert result.alerts_created == 1
    assert len(repo.saved) == 1
    assert repo.saved[0].kind == AlertKind.SPEND_SPIKE
    assert "2.5" in repo.saved[0].message or "ratio" in repo.saved[0].payload
    assert repo.saved[0].payload["current_spend_micros"] == current_spend
    assert repo.saved[0].payload["baseline_spend_micros"] == baseline_spend


@pytest.mark.asyncio
async def test_spend_spike_exactly_at_threshold_no_alert() -> None:
    """Current spend exactly at 2x baseline -> no alert (threshold is strict >)."""
    baseline_spend = 1_000_000
    current_spend = int(baseline_spend * _SPEND_SPIKE_MULTIPLIER)  # exactly 2x

    metrics = FakeHourlyMetrics(
        last_hours=[_metric(spend_micros=current_spend)],
        baseline=_metric(spend_micros=baseline_spend),
    )
    uc, repo = _make_uc(metrics)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    assert result.alerts_created == 0
    spend_alerts = [a for a in repo.saved if a.kind == AlertKind.SPEND_SPIKE]
    assert len(spend_alerts) == 0


@pytest.mark.asyncio
async def test_spend_below_threshold_no_alert() -> None:
    """Current spend 1.5x baseline -> no alert."""
    baseline_spend = 2_000_000
    current_spend = int(baseline_spend * 1.5)

    metrics = FakeHourlyMetrics(
        last_hours=[_metric(spend_micros=current_spend)],
        baseline=_metric(spend_micros=baseline_spend),
    )
    uc, _repo = _make_uc(metrics)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    assert result.alerts_created == 0


@pytest.mark.asyncio
async def test_spend_spike_zero_baseline_no_alert() -> None:
    """If baseline spend is 0, skip the spike check (no div-by-zero)."""
    metrics = FakeHourlyMetrics(
        last_hours=[_metric(spend_micros=5_000_000)],
        baseline=_metric(spend_micros=0),
    )
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    spend_alerts = [a for a in repo.saved if a.kind == AlertKind.SPEND_SPIKE]
    assert len(spend_alerts) == 0


# ── Test 2: Conversion drought ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_conversion_drought_triggers_alert() -> None:
    """6 consecutive zero-conversion hours with non-zero baseline → alert."""
    zero_hours = [
        _metric(hour=i, conversions=0.0, spend_micros=500_000)
        for i in range(_ZERO_CONVERSION_HOURS)
    ]
    metrics = FakeHourlyMetrics(
        last_hours=zero_hours,
        baseline=_metric(conversions=3.0),  # baseline expects conversions
    )
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    drought_alerts = [a for a in repo.saved if a.kind == AlertKind.CONVERSION_DROUGHT]
    assert len(drought_alerts) == 1
    assert drought_alerts[0].payload["consecutive_zero_hours"] == _ZERO_CONVERSION_HOURS
    assert drought_alerts[0].payload["baseline_conversions_per_hour"] == 3.0


@pytest.mark.asyncio
async def test_conversion_drought_fewer_hours_no_alert() -> None:
    """Only 5 zero-conversion hours → no alert (threshold is 6)."""
    zero_hours = [_metric(hour=i, conversions=0.0) for i in range(_ZERO_CONVERSION_HOURS - 1)]
    metrics = FakeHourlyMetrics(
        last_hours=zero_hours,
        baseline=_metric(conversions=5.0),
    )
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    drought_alerts = [a for a in repo.saved if a.kind == AlertKind.CONVERSION_DROUGHT]
    assert len(drought_alerts) == 0


@pytest.mark.asyncio
async def test_conversion_drought_baseline_zero_no_alert() -> None:
    """6 zero-conversion hours but baseline is also 0 → no alert (normal)."""
    zero_hours = [_metric(hour=i, conversions=0.0) for i in range(_ZERO_CONVERSION_HOURS)]
    metrics = FakeHourlyMetrics(
        last_hours=zero_hours,
        baseline=_metric(conversions=0.0),  # account never converts in this hour
    )
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    drought_alerts = [a for a in repo.saved if a.kind == AlertKind.CONVERSION_DROUGHT]
    assert len(drought_alerts) == 0


@pytest.mark.asyncio
async def test_conversion_drought_one_non_zero_hour_no_alert() -> None:
    """6 hours but one has conversions → drought not triggered."""
    hours = [_metric(hour=i, conversions=0.0) for i in range(_ZERO_CONVERSION_HOURS - 1)]
    hours.append(_metric(hour=_ZERO_CONVERSION_HOURS - 1, conversions=1.0))  # one hit
    metrics = FakeHourlyMetrics(
        last_hours=hours,
        baseline=_metric(conversions=3.0),
    )
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    drought_alerts = [a for a in repo.saved if a.kind == AlertKind.CONVERSION_DROUGHT]
    assert len(drought_alerts) == 0


# ── Test 3: Budget burning fast ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_budget_burning_fast_triggers_alert() -> None:
    """90% budget consumed before 14:00 UTC → alert."""
    status = DailyBudgetStatus(
        daily_budget_micros=10_000_000,
        spent_today_micros=9_000_000,  # 90%
        pct_consumed=90.0,
    )
    metrics = FakeHourlyMetrics(budget_statuses=[status])
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    budget_alerts = [a for a in repo.saved if a.kind == AlertKind.BUDGET_BURNING_FAST]
    assert len(budget_alerts) == 1
    assert budget_alerts[0].payload["avg_pct_consumed"] > 80


@pytest.mark.asyncio
async def test_budget_burning_fast_afternoon_no_alert() -> None:
    """90% budget consumed but it's already 15:00 UTC → no alert."""
    status = DailyBudgetStatus(
        daily_budget_micros=10_000_000,
        spent_today_micros=9_000_000,
        pct_consumed=90.0,
    )
    metrics = FakeHourlyMetrics(budget_statuses=[status])
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_AFTERNOON)

    budget_alerts = [a for a in repo.saved if a.kind == AlertKind.BUDGET_BURNING_FAST]
    assert len(budget_alerts) == 0


@pytest.mark.asyncio
async def test_budget_below_threshold_no_alert() -> None:
    """75% consumed before 14:00 UTC → below 80% threshold → no alert."""
    status = DailyBudgetStatus(
        daily_budget_micros=10_000_000,
        spent_today_micros=7_500_000,  # 75%
        pct_consumed=75.0,
    )
    metrics = FakeHourlyMetrics(budget_statuses=[status])
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    budget_alerts = [a for a in repo.saved if a.kind == AlertKind.BUDGET_BURNING_FAST]
    assert len(budget_alerts) == 0


# ── Test 4: Conversion tracking errors ───────────────────────────────────────


@pytest.mark.asyncio
async def test_tracking_error_triggers_alert() -> None:
    """has_errors=True → TRACKING_ERROR alert."""
    tracking = ConversionTrackingStatus(
        has_errors=True,
        error_detail="Tag errors on conversion action 'Purchase'",
    )
    metrics = FakeHourlyMetrics(tracking_status=tracking)
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    tracking_alerts = [a for a in repo.saved if a.kind == AlertKind.TRACKING_ERROR]
    assert len(tracking_alerts) == 1
    assert "Purchase" in tracking_alerts[0].message
    assert tracking_alerts[0].payload["error_detail"] == tracking.error_detail


@pytest.mark.asyncio
async def test_tracking_ok_no_alert() -> None:
    """has_errors=False → no alert."""
    tracking = ConversionTrackingStatus(has_errors=False, error_detail=None)
    metrics = FakeHourlyMetrics(tracking_status=tracking)
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    tracking_alerts = [a for a in repo.saved if a.kind == AlertKind.TRACKING_ERROR]
    assert len(tracking_alerts) == 0


# ── Test 5: Impression share drop ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_impression_share_drop_triggers_alert() -> None:
    """WoW IS dropped by 35 pp → IMPRESSION_SHARE_DROP alert."""
    metrics = FakeHourlyMetrics(is_wow=-0.35)  # -35 pp
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    is_alerts = [a for a in repo.saved if a.kind == AlertKind.IMPRESSION_SHARE_DROP]
    assert len(is_alerts) == 1
    assert is_alerts[0].payload["drop_pct"] == pytest.approx(35.0, abs=0.1)


@pytest.mark.asyncio
async def test_impression_share_small_drop_no_alert() -> None:
    """WoW IS dropped by 20 pp -> below threshold -> no alert."""
    metrics = FakeHourlyMetrics(is_wow=-0.20)
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    is_alerts = [a for a in repo.saved if a.kind == AlertKind.IMPRESSION_SHARE_DROP]
    assert len(is_alerts) == 0


@pytest.mark.asyncio
async def test_impression_share_improved_no_alert() -> None:
    """WoW IS increased -> no alert."""
    metrics = FakeHourlyMetrics(is_wow=0.10)
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    is_alerts = [a for a in repo.saved if a.kind == AlertKind.IMPRESSION_SHARE_DROP]
    assert len(is_alerts) == 0


@pytest.mark.asyncio
async def test_impression_share_unavailable_no_alert() -> None:
    """WoW IS not available (None) -> no alert."""
    metrics = FakeHourlyMetrics(is_wow=None)
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    is_alerts = [a for a in repo.saved if a.kind == AlertKind.IMPRESSION_SHARE_DROP]
    assert len(is_alerts) == 0


# ── Test 6: Rate limiting ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rate_limit_blocks_all_when_quota_full() -> None:
    """3 alerts already fired in 24h → all new anomalies suppressed."""
    tracking = ConversionTrackingStatus(has_errors=True, error_detail="tag error")
    baseline_spend = 1_000_000
    current_spend = int(baseline_spend * 3)  # spike
    zero_hours = [_metric(hour=i, conversions=0.0) for i in range(_ZERO_CONVERSION_HOURS)]
    budget_status = DailyBudgetStatus(
        daily_budget_micros=10_000_000,
        spent_today_micros=9_000_000,
        pct_consumed=90.0,
    )
    metrics = FakeHourlyMetrics(
        last_hours=[*zero_hours, _metric(spend_micros=current_spend)],
        baseline=_metric(spend_micros=baseline_spend, conversions=5.0),
        budget_statuses=[budget_status],
        tracking_status=tracking,
        is_wow=-0.40,
    )
    uc, repo = _make_uc(metrics, existing_alerts=_MAX_ALERTS_PER_DAY)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    assert result.alerts_created == 0
    assert result.alerts_suppressed > 0
    assert len(repo.saved) == 0  # nothing actually persisted


@pytest.mark.asyncio
async def test_rate_limit_partial_quota() -> None:
    """2 alerts already → only 1 more slot remains; second anomaly suppressed."""
    baseline_spend = 1_000_000
    current_spend = int(baseline_spend * 3)  # triggers SPEND_SPIKE
    tracking = ConversionTrackingStatus(
        has_errors=True, error_detail="err"
    )  # triggers TRACKING_ERROR

    metrics = FakeHourlyMetrics(
        last_hours=[_metric(spend_micros=current_spend)],
        baseline=_metric(spend_micros=baseline_spend),
        tracking_status=tracking,
    )
    uc, repo = _make_uc(metrics, existing_alerts=_MAX_ALERTS_PER_DAY - 1)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    # One slot left — first triggered anomaly gets created, second suppressed
    assert result.alerts_created == 1
    assert result.alerts_suppressed == 1
    assert len(repo.saved) == 1


@pytest.mark.asyncio
async def test_all_five_anomalies_three_created_two_suppressed() -> None:
    """All 5 anomalies trigger; max 3 alerts created, 2 suppressed.

    Construction:
    - 7-element last_hours list: 6 zero-conv hours + 1 high-spend zero-conv hour
    - get_last_n_hours(n=1) → [high_spend_hour] → SPEND_SPIKE triggered
    - get_last_n_hours(n=6) → [zero*5, high_spend_hour] — all conversions=0 → DROUGHT triggered
    """
    baseline_spend = 1_000_000
    current_spend = int(baseline_spend * 3)
    # Spike metric also has zero conversions so the drought window is all-zero
    spike_metric = _metric(spend_micros=current_spend, conversions=0.0)
    zero_hours = [_metric(hour=i, conversions=0.0) for i in range(_ZERO_CONVERSION_HOURS)]
    budget_status = DailyBudgetStatus(
        daily_budget_micros=10_000_000,
        spent_today_micros=9_000_000,
        pct_consumed=90.0,
    )
    tracking = ConversionTrackingStatus(has_errors=True, error_detail="pixel error")

    metrics = FakeHourlyMetrics(
        last_hours=[*zero_hours, spike_metric],
        baseline=_metric(spend_micros=baseline_spend, conversions=5.0),
        budget_statuses=[budget_status],
        tracking_status=tracking,
        is_wow=-0.50,
    )
    uc, repo = _make_uc(metrics, existing_alerts=0)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    assert result.checks_run == 5
    assert result.alerts_created == _MAX_ALERTS_PER_DAY  # 3
    assert result.alerts_suppressed == 2  # 5 triggers - 3 quota = 2 suppressed
    assert len(repo.saved) == _MAX_ALERTS_PER_DAY


# ── Test 7: Alert content and severity ───────────────────────────────────────


@pytest.mark.asyncio
async def test_alert_always_critical_severity() -> None:
    """Every alert is CRITICAL severity regardless of anomaly type."""
    from adcopilot.domain.alert import AlertSeverity

    tracking = ConversionTrackingStatus(has_errors=True, error_detail="err")
    metrics = FakeHourlyMetrics(tracking_status=tracking)
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    for alert in repo.saved:
        assert alert.severity == AlertSeverity.CRITICAL


@pytest.mark.asyncio
async def test_alert_account_id_matches() -> None:
    """Saved alerts carry the correct account_id."""
    tracking = ConversionTrackingStatus(has_errors=True, error_detail="err")
    metrics = FakeHourlyMetrics(tracking_status=tracking)
    uc, repo = _make_uc(metrics)
    await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    for alert in repo.saved:
        assert alert.account_id == _ACCOUNT_ID


@pytest.mark.asyncio
async def test_result_metadata() -> None:
    """AnomalyDetectionResult contains correct counts and account_id."""
    metrics = FakeHourlyMetrics()  # nothing triggers
    uc, _repo = _make_uc(metrics)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    assert result.account_id == str(_ACCOUNT_ID)
    assert result.checks_run == 5
    assert result.alerts_created == 0
    assert result.alerts_suppressed == 0


@pytest.mark.asyncio
async def test_no_anomalies_when_all_metrics_normal() -> None:
    """Clean metrics → zero alerts created."""
    metrics = FakeHourlyMetrics(
        last_hours=[_metric(spend_micros=1_000_000, conversions=5.0)],
        baseline=_metric(spend_micros=900_000, conversions=4.0),  # ~1.1x -- fine
        budget_statuses=[
            DailyBudgetStatus(
                daily_budget_micros=10_000_000,
                spent_today_micros=3_000_000,
                pct_consumed=30.0,
            )
        ],
        tracking_status=ConversionTrackingStatus(has_errors=False, error_detail=None),
        is_wow=-0.05,  # only -5 pp drop — fine
    )
    uc, repo = _make_uc(metrics)
    result = await uc.execute(_ACCOUNT_ID, _CUSTOMER_ID, _REFRESH_TOKEN, now=_NOW_MORNING)

    assert result.alerts_created == 0
    assert len(repo.saved) == 0
