from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
)


@dataclass
class SnapshotData:
    """All snapshot collections for one account on one date."""

    campaigns: list[CampaignSnapshot]
    ad_groups: list[AdGroupSnapshot]
    keywords: list[KeywordSnapshot]
    search_terms: list[SearchTermSnapshot]
    ads: list[AdSnapshot]
    negative_keywords: list[NegativeKeywordSnapshot] = field(default_factory=list)


class SnapshotRepository(Protocol):
    async def upsert_campaigns(
        self, account_id: AccountId, snapshots: list[CampaignSnapshot]
    ) -> None: ...

    async def upsert_ad_groups(
        self, account_id: AccountId, snapshots: list[AdGroupSnapshot]
    ) -> None: ...

    async def upsert_keywords(
        self, account_id: AccountId, snapshots: list[KeywordSnapshot]
    ) -> None: ...

    async def upsert_search_terms(
        self, account_id: AccountId, snapshots: list[SearchTermSnapshot]
    ) -> None: ...

    async def upsert_ads(
        self, account_id: AccountId, snapshots: list[AdSnapshot]
    ) -> None: ...

    async def get_latest_snapshot_date(
        self, account_id: AccountId
    ) -> date | None: ...

    async def load_snapshot(
        self, account_id: AccountId, snapshot_date: date
    ) -> SnapshotData: ...

    async def get_campaigns_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[CampaignSnapshot]: ...

    async def get_ad_groups_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[AdGroupSnapshot]: ...

    async def get_keywords_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[KeywordSnapshot]: ...

    async def get_ads_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[AdSnapshot]: ...

    async def upsert_negative_keywords(
        self, account_id: AccountId, snapshots: list[NegativeKeywordSnapshot]
    ) -> None: ...

    async def get_negative_keywords_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[NegativeKeywordSnapshot]: ...
