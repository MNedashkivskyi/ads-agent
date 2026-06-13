"""GoogleAdsPerformanceAdapter — one pull, three row types (AdsPerformancePort).

Returns per-asset, per-keyword, and search-term rows for an account+date range as
domain DTOs. Reuses the existing client/OAuth plumbing and runs the sync gRPC SDK
in a threadpool. Auth and rate-limit failures surface typed errors (so callers
can back off / skip) rather than raw SDK exceptions.
"""

from __future__ import annotations

import asyncio
from datetime import date

import structlog

from adcopilot.application.ports.ads_performance import (
    AssetPerformanceRow,
    KeywordPerformanceRow,
    SearchTermRow,
)
from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsRateLimited, GoogleAdsUnavailable
from adcopilot.infrastructure.google_ads.client import (
    GoogleAdsClientAdapter,
    is_google_auth_error,
    is_rate_limit_error,
)

logger = structlog.get_logger(__name__)


class GoogleAdsPerformanceAdapter:
    name = "google_ads_performance"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    async def fetch_asset_performance(
        self, refresh_token: str, customer_id: str, *, start_date: date, end_date: date
    ) -> list[AssetPerformanceRow]:
        query = (
            "SELECT segments.date, ad_group_ad_asset_view.field_type, "
            "ad_group_ad_asset_view.performance_label, asset.id, asset.text_asset.text, "
            "ad_group.id, campaign.id, metrics.impressions, metrics.clicks, "
            "metrics.conversions, metrics.cost_micros FROM ad_group_ad_asset_view "
            f"WHERE segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}' "
            "AND ad_group_ad_asset_view.field_type IN ('HEADLINE','DESCRIPTION')"
        )

        def _map(row: object) -> AssetPerformanceRow:
            return AssetPerformanceRow(
                account_id="",
                customer_id=customer_id,
                day=_parse_date(row.segments.date),  # type: ignore[attr-defined]
                asset_id=str(row.asset.id),  # type: ignore[attr-defined]
                asset_text=str(getattr(row.asset.text_asset, "text", "") or ""),  # type: ignore[attr-defined]
                field_type=row.ad_group_ad_asset_view.field_type.name,  # type: ignore[attr-defined]
                ad_group_id=str(row.ad_group.id),  # type: ignore[attr-defined]
                campaign_id=str(row.campaign.id),  # type: ignore[attr-defined]
                impressions=int(row.metrics.impressions),  # type: ignore[attr-defined]
                clicks=int(row.metrics.clicks),  # type: ignore[attr-defined]
                conversions=float(row.metrics.conversions),  # type: ignore[attr-defined]
                cost_micros=int(row.metrics.cost_micros),  # type: ignore[attr-defined]
                performance_label=row.ad_group_ad_asset_view.performance_label.name,  # type: ignore[attr-defined]
            )

        return await self._search(refresh_token, customer_id, query, _map)

    async def fetch_keyword_performance(
        self, refresh_token: str, customer_id: str, *, start_date: date, end_date: date
    ) -> list[KeywordPerformanceRow]:
        query = (
            "SELECT segments.date, ad_group_criterion.criterion_id, "
            "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, "
            "ad_group.id, campaign.id, metrics.impressions, metrics.clicks, "
            "metrics.conversions, metrics.cost_micros FROM keyword_view "
            f"WHERE segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'"
        )

        def _map(row: object) -> KeywordPerformanceRow:
            return KeywordPerformanceRow(
                account_id="",
                customer_id=customer_id,
                day=_parse_date(row.segments.date),  # type: ignore[attr-defined]
                criterion_id=str(row.ad_group_criterion.criterion_id),  # type: ignore[attr-defined]
                keyword_text=str(row.ad_group_criterion.keyword.text),  # type: ignore[attr-defined]
                match_type=row.ad_group_criterion.keyword.match_type.name,  # type: ignore[attr-defined]
                ad_group_id=str(row.ad_group.id),  # type: ignore[attr-defined]
                campaign_id=str(row.campaign.id),  # type: ignore[attr-defined]
                impressions=int(row.metrics.impressions),  # type: ignore[attr-defined]
                clicks=int(row.metrics.clicks),  # type: ignore[attr-defined]
                conversions=float(row.metrics.conversions),  # type: ignore[attr-defined]
                cost_micros=int(row.metrics.cost_micros),  # type: ignore[attr-defined]
            )

        return await self._search(refresh_token, customer_id, query, _map)

    async def fetch_search_terms(
        self, refresh_token: str, customer_id: str, *, start_date: date, end_date: date
    ) -> list[SearchTermRow]:
        query = (
            "SELECT segments.date, search_term_view.search_term, search_term_view.status, "
            "segments.keyword.info.text, ad_group.id, campaign.id, metrics.impressions, "
            "metrics.clicks, metrics.conversions, metrics.cost_micros FROM search_term_view "
            f"WHERE segments.date BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'"
        )

        def _map(row: object) -> SearchTermRow:
            return SearchTermRow(
                account_id="",
                customer_id=customer_id,
                day=_parse_date(row.segments.date),  # type: ignore[attr-defined]
                search_term=str(row.search_term_view.search_term),  # type: ignore[attr-defined]
                matched_keyword_text=str(getattr(row.segments.keyword.info, "text", "") or ""),  # type: ignore[attr-defined]
                ad_group_id=str(row.ad_group.id),  # type: ignore[attr-defined]
                campaign_id=str(row.campaign.id),  # type: ignore[attr-defined]
                impressions=int(row.metrics.impressions),  # type: ignore[attr-defined]
                clicks=int(row.metrics.clicks),  # type: ignore[attr-defined]
                conversions=float(row.metrics.conversions),  # type: ignore[attr-defined]
                cost_micros=int(row.metrics.cost_micros),  # type: ignore[attr-defined]
                status=row.search_term_view.status.name,  # type: ignore[attr-defined]
            )

        return await self._search(refresh_token, customer_id, query, _map)

    async def _search(self, refresh_token: str, customer_id: str, query: str, mapper):  # noqa: ANN001, ANN202
        def _blocking() -> list:
            try:
                client = self._client._build_client(refresh_token)
                service = client.get_service("GoogleAdsService")
                response = service.search(
                    customer_id=customer_id.replace("-", ""), query=query
                )
                return [mapper(row) for row in response]
            except Exception as exc:  # noqa: BLE001
                if is_google_auth_error(exc):
                    raise GoogleAdsAuthError(str(exc)) from exc
                if is_rate_limit_error(exc):
                    raise GoogleAdsRateLimited(str(exc)) from exc
                raise GoogleAdsUnavailable(str(exc)) from exc

        return await asyncio.wait_for(asyncio.to_thread(_blocking), timeout=120)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)
