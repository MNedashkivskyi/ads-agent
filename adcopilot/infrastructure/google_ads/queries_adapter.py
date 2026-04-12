"""Adapter that implements GoogleAdsClientPort by delegating to query functions."""

from datetime import date

from adcopilot.application.ports.google_ads import CustomerInfo
from adcopilot.config import Settings
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
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
