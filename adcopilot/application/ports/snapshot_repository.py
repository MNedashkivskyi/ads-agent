from datetime import date
from typing import Protocol

from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
)


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
