"""GA4 Data API adapter — pulls page-level metrics for a given date range."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date

import structlog

logger = structlog.get_logger(__name__)

GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"


@dataclass
class GA4PageMetrics:
    page_path: str
    sessions: int
    bounce_rate: float | None
    avg_session_duration_sec: float | None
    pages_per_session: float | None


async def fetch_page_metrics(
    property_id: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    snapshot_date: date,
) -> list[GA4PageMetrics]:
    """Fetch per-page metrics from GA4 Data API for a single day."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        _fetch_sync,
        property_id,
        refresh_token,
        client_id,
        client_secret,
        snapshot_date,
    )


def _fetch_sync(
    property_id: str,
    refresh_token: str,
    client_id: str,
    client_secret: str,
    snapshot_date: date,
) -> list[GA4PageMetrics]:
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            RunReportRequest,
        )
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
        client = BetaAnalyticsDataClient(credentials=creds)
        date_str = snapshot_date.isoformat()
        request = RunReportRequest(
            property=f"properties/{property_id}",
            dimensions=[Dimension(name="pagePath")],
            metrics=[
                Metric(name="sessions"),
                Metric(name="bounceRate"),
                Metric(name="averageSessionDuration"),
                Metric(name="screenPageViewsPerSession"),
            ],
            date_ranges=[DateRange(start_date=date_str, end_date=date_str)],
            limit=500,
        )
        response = client.run_report(request)
        results: list[GA4PageMetrics] = []
        for row in response.rows:
            path = row.dimension_values[0].value
            sessions = int(row.metric_values[0].value or 0)
            bounce = _float_or_none(row.metric_values[1].value)
            duration = _float_or_none(row.metric_values[2].value)
            pps = _float_or_none(row.metric_values[3].value)
            results.append(
                GA4PageMetrics(
                    page_path=path,
                    sessions=sessions,
                    bounce_rate=bounce,
                    avg_session_duration_sec=duration,
                    pages_per_session=pps,
                )
            )
        return results
    except Exception as exc:
        logger.warning("ga4_fetch_failed", error=str(exc))
        return []


def _float_or_none(val: str) -> float | None:
    try:
        return float(val) if val else None
    except (ValueError, TypeError):
        return None
