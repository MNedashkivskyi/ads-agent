"""Google Ads adapter for hourly anomaly-detection metrics.

Implements HourlyMetricsPort by issuing GAQL queries segmented by hour.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from adcopilot.application.ports.hourly_metrics import (
    ConversionTrackingStatus,
    DailyBudgetStatus,
    HourlyMetric,
)
from adcopilot.config import Settings
from adcopilot.domain.entities import AccountId
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter


class GoogleAdsHourlyMetricsAdapter:
    """Production implementation of HourlyMetricsPort.

    All I/O is synchronous under the hood (google-ads library) wrapped in
    asyncio.to_thread so the event loop is never blocked.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client_adapter = GoogleAdsClientAdapter(settings)

    def _build_client(self, refresh_token: str) -> object:
        return self._client_adapter._build_client(refresh_token)

    # ── public interface ─────────────────────────────────────────────────────

    async def get_last_n_hours(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        n: int,
    ) -> list[HourlyMetric]:
        cid = customer_id.replace("-", "")
        return await asyncio.to_thread(self._query_last_n_hours_sync, cid, refresh_token, n)

    async def get_baseline_for_hour(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
        hour_of_day: int,
        day_of_week: int,
        lookback_days: int = 7,
    ) -> HourlyMetric | None:
        cid = customer_id.replace("-", "")
        return await asyncio.to_thread(
            self._query_baseline_sync,
            cid,
            refresh_token,
            hour_of_day,
            day_of_week,
            lookback_days,
        )

    async def get_daily_budget_status(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
    ) -> list[DailyBudgetStatus]:
        cid = customer_id.replace("-", "")
        return await asyncio.to_thread(self._query_daily_budget_sync, cid, refresh_token)

    async def get_conversion_tracking_status(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
    ) -> ConversionTrackingStatus:
        cid = customer_id.replace("-", "")
        return await asyncio.to_thread(self._query_tracking_status_sync, cid, refresh_token)

    async def get_impression_share_wow(
        self,
        account_id: AccountId,
        customer_id: str,
        refresh_token: str,
    ) -> float | None:
        cid = customer_id.replace("-", "")
        return await asyncio.to_thread(self._query_is_wow_sync, cid, refresh_token)

    # ── sync helpers (run in thread-pool) ───────────────────────────────────

    def _query_last_n_hours_sync(self, cid: str, refresh_token: str, n: int) -> list[HourlyMetric]:
        client = self._build_client(refresh_token)
        ga_service = client.get_service("GoogleAdsService")  # type: ignore[attr-defined]

        now_utc = datetime.now(UTC)
        # Query full calendar days that contain the last n hours.
        # We over-fetch and filter in Python to keep the GAQL simple.
        today = now_utc.date().isoformat()
        yesterday = (now_utc - timedelta(days=1)).date().isoformat()

        query = f"""
            SELECT
                segments.date,
                segments.hour,
                metrics.cost_micros,
                metrics.conversions,
                metrics.impressions,
                metrics.search_impression_share
            FROM campaign
            WHERE segments.date IN ('{yesterday}', '{today}')
              AND campaign.status = 'ENABLED'
            ORDER BY segments.date, segments.hour
        """
        response = ga_service.search(customer_id=cid, query=query)  # type: ignore[attr-defined]

        # Aggregate across campaigns per hour
        from collections import defaultdict

        hour_data: dict[tuple[str, int], dict[str, float]] = defaultdict(
            lambda: {
                "spend": 0.0,
                "conversions": 0.0,
                "impressions": 0.0,
                "is_sum": 0.0,
                "is_cnt": 0,
            }
        )
        for row in response:
            key = (row.segments.date, row.segments.hour)
            hour_data[key]["spend"] += row.metrics.cost_micros
            hour_data[key]["conversions"] += row.metrics.conversions
            hour_data[key]["impressions"] += row.metrics.impressions
            is_val = row.metrics.search_impression_share
            if is_val and 0 <= is_val <= 1:
                hour_data[key]["is_sum"] += is_val
                hour_data[key]["is_cnt"] += 1

        # Build sorted list and return last n
        metrics: list[HourlyMetric] = []
        for (date_str, hour), data in sorted(hour_data.items()):
            is_val_avg = data["is_sum"] / data["is_cnt"] if data["is_cnt"] > 0 else None
            metrics.append(
                HourlyMetric(
                    date=date_str,
                    hour=hour,
                    spend_micros=int(data["spend"]),
                    conversions=data["conversions"],
                    impressions=int(data["impressions"]),
                    impression_share=is_val_avg,
                )
            )

        return metrics[-n:] if len(metrics) >= n else metrics

    def _query_baseline_sync(
        self,
        cid: str,
        refresh_token: str,
        hour_of_day: int,
        day_of_week: int,
        lookback_days: int,
    ) -> HourlyMetric | None:
        """Rolling average for the same hour+weekday over the last N days."""
        client = self._build_client(refresh_token)
        ga_service = client.get_service("GoogleAdsService")  # type: ignore[attr-defined]

        now_utc = datetime.now(UTC)
        # Build list of dates in the lookback window that match the target weekday
        # Python weekday(): 0=Monday … 6=Sunday
        target_dates: list[str] = []
        check = now_utc.date() - timedelta(days=1)  # start from yesterday
        for _ in range(lookback_days * 2):  # generous range to find 7 matching days
            if check.weekday() == day_of_week:
                target_dates.append(check.isoformat())
                if len(target_dates) >= lookback_days:
                    break
            check -= timedelta(days=1)

        if not target_dates:
            return None

        date_list = ", ".join(f"'{d}'" for d in target_dates)
        query = f"""
            SELECT
                segments.date,
                segments.hour,
                metrics.cost_micros,
                metrics.conversions,
                metrics.impressions,
                metrics.search_impression_share
            FROM campaign
            WHERE segments.date IN ({date_list})
              AND segments.hour = {hour_of_day}
              AND campaign.status = 'ENABLED'
        """
        response = ga_service.search(customer_id=cid, query=query)  # type: ignore[attr-defined]

        totals = {
            "spend": 0.0,
            "conversions": 0.0,
            "impressions": 0.0,
            "is_sum": 0.0,
            "is_cnt": 0,
            "rows": 0,
        }
        for row in response:
            totals["spend"] += row.metrics.cost_micros
            totals["conversions"] += row.metrics.conversions
            totals["impressions"] += row.metrics.impressions
            is_val = row.metrics.search_impression_share
            if is_val and 0 <= is_val <= 1:
                totals["is_sum"] += is_val
                totals["is_cnt"] += 1
            totals["rows"] += 1

        n_days = len(target_dates)
        if n_days == 0:
            return None

        is_avg = totals["is_sum"] / totals["is_cnt"] if totals["is_cnt"] > 0 else None
        return HourlyMetric(
            date="baseline",
            hour=hour_of_day,
            spend_micros=int(totals["spend"] / n_days),
            conversions=totals["conversions"] / n_days,
            impressions=int(totals["impressions"] / n_days),
            impression_share=is_avg,
        )

    def _query_daily_budget_sync(self, cid: str, refresh_token: str) -> list[DailyBudgetStatus]:
        client = self._build_client(refresh_token)
        ga_service = client.get_service("GoogleAdsService")  # type: ignore[attr-defined]

        today = datetime.now(UTC).date().isoformat()
        query = f"""
            SELECT
                campaign_budget.amount_micros,
                metrics.cost_micros
            FROM campaign
            WHERE campaign.status = 'ENABLED'
              AND segments.date = '{today}'
        """
        response = ga_service.search(customer_id=cid, query=query)  # type: ignore[attr-defined]

        statuses: list[DailyBudgetStatus] = []
        for row in response:
            budget = row.campaign_budget.amount_micros
            spent = row.metrics.cost_micros
            if budget <= 0:
                continue
            pct = spent / budget * 100
            statuses.append(
                DailyBudgetStatus(
                    daily_budget_micros=int(budget),
                    spent_today_micros=int(spent),
                    pct_consumed=pct,
                )
            )
        return statuses

    def _query_tracking_status_sync(self, cid: str, refresh_token: str) -> ConversionTrackingStatus:
        client = self._build_client(refresh_token)
        ga_service = client.get_service("GoogleAdsService")  # type: ignore[attr-defined]

        query = """
            SELECT
                conversion_action.name,
                conversion_action.status,
                conversion_action.tag_snippets
            FROM conversion_action
            WHERE conversion_action.status = 'ENABLED'
        """
        try:
            response = ga_service.search(customer_id=cid, query=query)  # type: ignore[attr-defined]
            for row in response:
                for snippet in row.conversion_action.tag_snippets:
                    if snippet.global_site_tag_errors or snippet.event_snippet_errors:
                        return ConversionTrackingStatus(
                            has_errors=True,
                            error_detail=(
                                f"Tag errors on conversion action '{row.conversion_action.name}'"
                            ),
                        )
        except Exception as exc:
            return ConversionTrackingStatus(
                has_errors=True,
                error_detail=f"API error querying conversion tracking: {exc}",
            )
        return ConversionTrackingStatus(has_errors=False, error_detail=None)

    def _query_is_wow_sync(self, cid: str, refresh_token: str) -> float | None:
        """Return week-over-week impression share change (negative = drop)."""
        client = self._build_client(refresh_token)
        ga_service = client.get_service("GoogleAdsService")  # type: ignore[attr-defined]

        now_utc = datetime.now(UTC).date()
        this_week_end = (now_utc - timedelta(days=1)).isoformat()
        this_week_start = (now_utc - timedelta(days=7)).isoformat()
        last_week_end = (now_utc - timedelta(days=8)).isoformat()
        last_week_start = (now_utc - timedelta(days=14)).isoformat()

        def _avg_is(start: str, end: str) -> float | None:
            query = f"""
                SELECT metrics.search_impression_share
                FROM campaign
                WHERE segments.date BETWEEN '{start}' AND '{end}'
                  AND campaign.status = 'ENABLED'
            """
            response = ga_service.search(customer_id=cid, query=query)  # type: ignore[attr-defined]
            values = []
            for row in response:
                val = row.metrics.search_impression_share
                if val and 0 <= val <= 1:
                    values.append(val)
            return sum(values) / len(values) if values else None

        this_avg = _avg_is(this_week_start, this_week_end)
        last_avg = _avg_is(last_week_start, last_week_end)

        if this_avg is None or last_avg is None or last_avg == 0:
            return None
        return this_avg - last_avg  # negative means drop
