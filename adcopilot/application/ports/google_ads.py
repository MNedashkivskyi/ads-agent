from dataclasses import dataclass
from datetime import date
from typing import Protocol

from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
)


@dataclass(frozen=True)
class CustomerInfo:
    descriptive_name: str
    currency: str
    timezone: str
    is_manager: bool


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
