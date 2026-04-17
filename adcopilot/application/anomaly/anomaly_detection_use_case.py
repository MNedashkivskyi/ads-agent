"""Hourly anomaly detection use case.

Runs every hour for every active account. Checks 5 anomaly conditions and
creates CRITICAL Alert rows when triggered. Rate-limited to 3 alerts per
account per 24 hours to prevent alert fatigue.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from adcopilot.application.ports.alert_repository import AlertRepository
from adcopilot.application.ports.hourly_metrics import HourlyMetricsPort
from adcopilot.domain.alert import Alert, AlertId, AlertKind, AlertSeverity, AlertStatus
from adcopilot.domain.entities import AccountId

logger = structlog.get_logger(__name__)

# ── Thresholds ───────────────────────────────────────────────────────────────
_SPEND_SPIKE_MULTIPLIER = 2.0  # current > 2x baseline -> anomaly
_ZERO_CONVERSION_HOURS = 6  # consecutive zero-conversion hours
_BUDGET_BURN_THRESHOLD_PCT = 80.0  # >80 % budget consumed before 14:00 local
_BUDGET_BURN_HOUR_LOCAL = 14  # 2 pm local time
_IS_DROP_THRESHOLD = -0.30  # impression share dropped by >30 pp
_MAX_ALERTS_PER_DAY = 3  # rate limit per account


@dataclass(frozen=True)
class AnomalyDetectionResult:
    account_id: str
    alerts_created: int
    alerts_suppressed: int
    checks_run: int


class AnomalyDetectionUseCase:
    """Detect real-time anomalies in Google Ads performance.

    Called once per account from the hourly Celery task.  Each invocation:
    1. Checks current quota (<= 3 alerts / 24 h per account).
    2. Runs all 5 anomaly checks.
    3. Creates an Alert row for each triggered anomaly (up to quota).
    """

    def __init__(
        self,
        metrics: HourlyMetricsPort,
        alert_repo: AlertRepository,
    ) -> None:
        self._metrics = metrics
        self._alert_repo = alert_repo

    async def execute(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        *,
        now: datetime | None = None,
    ) -> AnomalyDetectionResult:
        """Run all anomaly checks for one account.

        Parameters
        ----------
        account_id:
            Internal UUID-backed account identifier.
        customer_id:
            Google Ads customer ID (may contain hyphens).
        refresh_token:
            OAuth2 refresh token for the account.
        now:
            Override for the current time (useful in tests).
        """
        if now is None:
            now = datetime.now(UTC)

        log = logger.bind(account_id=str(account_id))

        # ── Rate-limit guard ────────────────────────────────────────────────
        since_24h = now - timedelta(hours=24)
        existing_count = await self._alert_repo.count_since(account_id, since_24h)
        remaining_quota = _MAX_ALERTS_PER_DAY - existing_count

        checks_run = 0
        alerts_created = 0
        alerts_suppressed = 0

        async def _maybe_create(kind: AlertKind, message: str, payload: dict[str, Any]) -> None:
            nonlocal alerts_created, alerts_suppressed
            if alerts_created >= remaining_quota:
                alerts_suppressed += 1
                log.warning(
                    "anomaly suppressed (rate limit)",
                    kind=kind.value,
                    remaining_quota=remaining_quota,
                )
                return
            alert = Alert(
                id=AlertId(str(uuid.uuid4())),
                account_id=account_id,
                kind=kind,
                severity=AlertSeverity.CRITICAL,
                status=AlertStatus.OPEN,
                payload=payload,
                message=message,
                created_at=now,  # type: ignore[arg-type]
            )
            await self._alert_repo.save(alert)
            alerts_created += 1
            log.warning("alert created", kind=kind.value, message=message)

        # ── Check 1: Spend spike ────────────────────────────────────────────
        checks_run += 1
        try:
            await self._check_spend_spike(
                account_id, customer_id, refresh_token, now, _maybe_create
            )
        except Exception:
            log.exception("spend_spike check failed (non-fatal)")

        # ── Check 2: Conversion drought ─────────────────────────────────────
        checks_run += 1
        try:
            await self._check_conversion_drought(
                account_id, customer_id, refresh_token, now, _maybe_create
            )
        except Exception:
            log.exception("conversion_drought check failed (non-fatal)")

        # ── Check 3: Budget burning fast ─────────────────────────────────────
        checks_run += 1
        try:
            await self._check_budget_burning_fast(
                account_id, customer_id, refresh_token, now, _maybe_create
            )
        except Exception:
            log.exception("budget_burning_fast check failed (non-fatal)")

        # ── Check 4: Conversion tracking errors ─────────────────────────────
        checks_run += 1
        try:
            await self._check_tracking_errors(
                account_id, customer_id, refresh_token, now, _maybe_create
            )
        except Exception:
            log.exception("tracking_errors check failed (non-fatal)")

        # ── Check 5: Impression share drop ───────────────────────────────────
        checks_run += 1
        try:
            await self._check_impression_share_drop(
                account_id, customer_id, refresh_token, now, _maybe_create
            )
        except Exception:
            log.exception("impression_share_drop check failed (non-fatal)")

        return AnomalyDetectionResult(
            account_id=str(account_id),
            alerts_created=alerts_created,
            alerts_suppressed=alerts_suppressed,
            checks_run=checks_run,
        )

    # ── Internal check methods ───────────────────────────────────────────────

    async def _check_spend_spike(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        now: datetime,
        create: Any,
    ) -> None:
        """Anomaly: spend in last hour > 2x rolling 7-day baseline."""
        recent = await self._metrics.get_last_n_hours(account_id, customer_id, refresh_token, n=1)
        if not recent:
            return
        current = recent[-1]
        baseline = await self._metrics.get_baseline_for_hour(
            account_id,
            customer_id,
            refresh_token,
            hour_of_day=current.hour,
            day_of_week=now.weekday(),
        )
        if baseline is None or baseline.spend_micros == 0:
            return
        ratio = current.spend_micros / baseline.spend_micros
        if ratio > _SPEND_SPIKE_MULTIPLIER:
            current_pln = current.spend_micros / 1_000_000
            baseline_pln = baseline.spend_micros / 1_000_000
            await create(
                AlertKind.SPEND_SPIKE,
                f"Spend {current_pln:.2f} PLN in last hour is {ratio:.1f}x the "
                f"{baseline_pln:.2f} PLN baseline (threshold: {_SPEND_SPIKE_MULTIPLIER}x).",
                {
                    "current_spend_micros": current.spend_micros,
                    "baseline_spend_micros": baseline.spend_micros,
                    "ratio": round(ratio, 3),
                    "hour": current.hour,
                },
            )

    async def _check_conversion_drought(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        now: datetime,
        create: Any,
    ) -> None:
        """Anomaly: 0 conversions for 6+ consecutive hours when baseline >0."""
        hours = await self._metrics.get_last_n_hours(
            account_id, customer_id, refresh_token, n=_ZERO_CONVERSION_HOURS
        )
        if len(hours) < _ZERO_CONVERSION_HOURS:
            return

        # All hours must have zero conversions
        if any(h.conversions > 0 for h in hours):
            return

        # Verify baseline suggests conversions should be expected
        # Use the earliest of the checked hours for the baseline hour
        earliest = hours[0]
        baseline = await self._metrics.get_baseline_for_hour(
            account_id,
            customer_id,
            refresh_token,
            hour_of_day=earliest.hour,
            day_of_week=now.weekday(),
        )
        if baseline is None or baseline.conversions == 0:
            return

        await create(
            AlertKind.CONVERSION_DROUGHT,
            f"Zero conversions for {_ZERO_CONVERSION_HOURS} consecutive hours "
            f"(baseline expected {baseline.conversions:.2f}/h).",
            {
                "consecutive_zero_hours": _ZERO_CONVERSION_HOURS,
                "baseline_conversions_per_hour": round(baseline.conversions, 3),
                "hours_checked": [{"date": h.date, "hour": h.hour} for h in hours],
            },
        )

    async def _check_budget_burning_fast(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        now: datetime,
        create: Any,
    ) -> None:
        """Anomaly: >80 % of daily budget consumed before 2 pm local time."""
        # We compare UTC hour; if the account uses a local timezone we approximate
        # by checking UTC < 14. Implementors can refine via account timezone.
        if now.hour >= _BUDGET_BURN_HOUR_LOCAL:
            return  # Already afternoon — normal to be nearly spent

        statuses = await self._metrics.get_daily_budget_status(
            account_id, customer_id, refresh_token
        )
        triggered = [s for s in statuses if s.pct_consumed > _BUDGET_BURN_THRESHOLD_PCT]
        if not triggered:
            return

        total_budget = sum(s.daily_budget_micros for s in triggered)
        total_spent = sum(s.spent_today_micros for s in triggered)
        avg_pct = (total_spent / total_budget * 100) if total_budget > 0 else 0.0
        await create(
            AlertKind.BUDGET_BURNING_FAST,
            f"{len(triggered)} campaign(s) have consumed {avg_pct:.0f}% of their "
            f"daily budget before {_BUDGET_BURN_HOUR_LOCAL}:00 UTC.",
            {
                "campaigns_over_threshold": len(triggered),
                "avg_pct_consumed": round(avg_pct, 1),
                "threshold_pct": _BUDGET_BURN_THRESHOLD_PCT,
                "check_hour_utc": now.hour,
            },
        )

    async def _check_tracking_errors(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        now: datetime,
        create: Any,
    ) -> None:
        """Anomaly: conversion tracking pixel returning errors."""
        status = await self._metrics.get_conversion_tracking_status(
            account_id, customer_id, refresh_token
        )
        if not status.has_errors:
            return
        await create(
            AlertKind.TRACKING_ERROR,
            f"Conversion tracking error detected: {status.error_detail or 'unknown error'}.",
            {
                "error_detail": status.error_detail,
            },
        )

    async def _check_impression_share_drop(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        now: datetime,
        create: Any,
    ) -> None:
        """Anomaly: impression share dropped >30 pp week-over-week."""
        wow_change = await self._metrics.get_impression_share_wow(
            account_id, customer_id, refresh_token
        )
        if wow_change is None:
            return
        if wow_change > _IS_DROP_THRESHOLD:
            return  # Drop is not severe enough (or share improved)
        drop_pct = abs(wow_change) * 100
        await create(
            AlertKind.IMPRESSION_SHARE_DROP,
            f"Impression share dropped {drop_pct:.1f} percentage points week-over-week "
            f"(threshold: {abs(_IS_DROP_THRESHOLD) * 100:.0f} pp).",
            {
                "wow_change": round(wow_change, 4),
                "drop_pct": round(drop_pct, 1),
                "threshold_pct": abs(_IS_DROP_THRESHOLD) * 100,
            },
        )
