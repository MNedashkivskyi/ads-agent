"""Adapter that implements GoogleAdsClientPort by delegating to query functions."""

from datetime import date

from adcopilot.application.ports.google_ads import CustomerInfo, MerchantCenterLink
from adcopilot.config import Settings
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    AudiencePerformanceSnapshot,
    CampaignExtensionSnapshot,
    CampaignSnapshot,
    ConversionActionSnapshot,
    DayOfWeekPerformanceSnapshot,
    DevicePerformanceSnapshot,
    GeoPerformanceSnapshot,
    HourPerformanceSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
    SitelinkPerformanceSnapshot,
)
from adcopilot.infrastructure.google_ads import queries
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter


class GoogleAdsQueriesAdapter:
    """Full implementation of GoogleAdsClientPort combining client + query functions."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    async def list_accessible_customers(self, refresh_token: str) -> list[str]:
        return await self._client.list_accessible_customers(refresh_token)

    async def get_customer_info(self, refresh_token: str, customer_id: str) -> CustomerInfo:
        return await self._client.get_customer_info(refresh_token, customer_id)

    async def query_campaigns(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[CampaignSnapshot]:
        return await queries.query_campaigns(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_ad_groups(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdGroupSnapshot]:
        return await queries.query_ad_groups(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[KeywordSnapshot]:
        return await queries.query_keywords(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_search_terms(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[SearchTermSnapshot]:
        return await queries.query_search_terms(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_ads(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdSnapshot]:
        return await queries.query_ads(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_negative_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[NegativeKeywordSnapshot]:
        return await queries.query_negative_keywords(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_device_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DevicePerformanceSnapshot]:
        return await queries.query_device_performance(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_geo_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[GeoPerformanceSnapshot]:
        return await queries.query_geo_performance(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_hour_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[HourPerformanceSnapshot]:
        return await queries.query_hour_performance(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_day_of_week_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DayOfWeekPerformanceSnapshot]:
        return await queries.query_day_of_week_performance(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_audience_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AudiencePerformanceSnapshot]:
        return await queries.query_audience_performance(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_conversion_actions(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[ConversionActionSnapshot]:
        return await queries.query_conversion_actions(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_campaign_extensions(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[CampaignExtensionSnapshot]:
        return await queries.query_campaign_extensions(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_sitelink_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[SitelinkPerformanceSnapshot]:
        return await queries.query_sitelink_performance(
            refresh_token, customer_id, snapshot_date, self._settings
        )

    async def query_remarketing_lists(
        self, refresh_token: str, customer_id: str
    ) -> list:
        return await queries.query_remarketing_lists(
            refresh_token, customer_id, self._settings
        )

    async def list_conversion_actions(
        self, refresh_token: str, customer_id: str
    ) -> list[ConversionActionSnapshot]:
        return await queries.list_conversion_actions(
            refresh_token, customer_id, self._settings
        )

    async def list_recent_search_terms(
        self,
        refresh_token: str,
        customer_id: str,
        days: int = 7,
        limit: int = 20,
    ) -> list[SearchTermSnapshot]:
        return await queries.list_recent_search_terms(
            refresh_token, customer_id, self._settings, days=days, limit=limit
        )

    async def fetch_ad_metrics(
        self,
        refresh_token: str,
        customer_id: str,
        ad_resource_name: str,
        days: int = 7,
    ) -> dict:
        return await queries.fetch_ad_metrics(
            refresh_token, customer_id, ad_resource_name, self._settings, days=days
        )

    async def get_merchant_center_link(
        self, refresh_token: str, customer_id: str
    ) -> MerchantCenterLink | None:
        links = await queries.query_merchant_center_feed(
            refresh_token, customer_id, self._settings
        )
        for link in links:
            if str(link.get("status", "")).upper() in ("ENABLED", "PENDING"):
                return MerchantCenterLink(
                    merchant_id=int(link["feed_id"]),
                    account_name=str(link.get("name", "")),
                    status=str(link.get("status", "")),
                )
        return None

    async def fetch_auction_insights(
        self, refresh_token: str, customer_id: str, snapshot_date: "date"
    ) -> list[dict]:
        return await queries.fetch_auction_insights(
            refresh_token, customer_id, self._settings, snapshot_date
        )
