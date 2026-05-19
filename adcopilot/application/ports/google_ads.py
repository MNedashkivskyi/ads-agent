from dataclasses import dataclass
from datetime import date
from typing import Protocol

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
    RemarketingListInfo,
    SearchTermSnapshot,
    SitelinkPerformanceSnapshot,
)


@dataclass(frozen=True)
class CustomerInfo:
    descriptive_name: str
    currency: str
    timezone: str
    is_manager: bool


@dataclass(frozen=True)
class MerchantCenterLink:
    merchant_id: int
    account_name: str
    status: str  # e.g. "ENABLED", "PENDING"


class GoogleAdsClientPort(Protocol):
    async def list_accessible_customers(self, refresh_token: str) -> list[str]: ...

    async def get_customer_info(
        self, refresh_token: str, customer_id: str
    ) -> CustomerInfo: ...

    async def query_campaigns(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[CampaignSnapshot]: ...

    async def query_ad_groups(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdGroupSnapshot]: ...

    async def query_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[KeywordSnapshot]: ...

    async def query_search_terms(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[SearchTermSnapshot]: ...

    async def query_ads(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AdSnapshot]: ...

    async def query_negative_keywords(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[NegativeKeywordSnapshot]: ...

    async def query_device_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DevicePerformanceSnapshot]: ...

    async def query_geo_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[GeoPerformanceSnapshot]: ...

    async def query_hour_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[HourPerformanceSnapshot]: ...

    async def query_day_of_week_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[DayOfWeekPerformanceSnapshot]: ...

    async def query_audience_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[AudiencePerformanceSnapshot]: ...

    async def query_conversion_actions(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[ConversionActionSnapshot]: ...

    async def query_campaign_extensions(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[CampaignExtensionSnapshot]: ...

    async def query_sitelink_performance(
        self, refresh_token: str, customer_id: str, snapshot_date: date
    ) -> list[SitelinkPerformanceSnapshot]: ...

    async def query_remarketing_lists(
        self, refresh_token: str, customer_id: str
    ) -> list[RemarketingListInfo]: ...

    async def list_conversion_actions(
        self, refresh_token: str, customer_id: str
    ) -> list[ConversionActionSnapshot]: ...

    async def list_recent_search_terms(
        self,
        refresh_token: str,
        customer_id: str,
        days: int = 7,
        limit: int = 20,
    ) -> list[SearchTermSnapshot]: ...

    async def get_merchant_center_link(
        self, refresh_token: str, customer_id: str
    ) -> "MerchantCenterLink | None": ...
