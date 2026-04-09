"""SQLAlchemy implementation of SnapshotRepository using INSERT … ON CONFLICT DO UPDATE."""

import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    SearchTermSnapshot,
)
from adcopilot.infrastructure.db.models import (
    AdGroupSnapshotModel,
    AdSnapshotModel,
    CampaignSnapshotModel,
    KeywordSnapshotModel,
    SearchTermSnapshotModel,
)


class SqlSnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Campaigns
    # ------------------------------------------------------------------

    async def upsert_campaigns(
        self, account_id: AccountId, snapshots: list[CampaignSnapshot]
    ) -> None:
        if not snapshots:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "account_id": uuid.UUID(account_id),
                "snapshot_date": s.snapshot_date,
                "campaign_id": s.campaign_id,
                "name": s.name,
                "status": s.status,
                "channel_type": s.channel_type,
                "budget_micros": s.budget_micros,
                "bidding_strategy": s.bidding_strategy,
                "impressions": s.impressions,
                "clicks": s.clicks,
                "cost_micros": s.cost_micros,
                "conversions": s.conversions,
                "conv_value": s.conv_value,
            }
            for s in snapshots
        ]
        stmt = insert(CampaignSnapshotModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_campaign_snapshots",
            set_={
                "name": stmt.excluded.name,
                "status": stmt.excluded.status,
                "channel_type": stmt.excluded.channel_type,
                "budget_micros": stmt.excluded.budget_micros,
                "bidding_strategy": stmt.excluded.bidding_strategy,
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "cost_micros": stmt.excluded.cost_micros,
                "conversions": stmt.excluded.conversions,
                "conv_value": stmt.excluded.conv_value,
                "updated_at": text("now()"),
            },
        )
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Ad groups
    # ------------------------------------------------------------------

    async def upsert_ad_groups(
        self, account_id: AccountId, snapshots: list[AdGroupSnapshot]
    ) -> None:
        if not snapshots:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "account_id": uuid.UUID(account_id),
                "snapshot_date": s.snapshot_date,
                "ad_group_id": s.ad_group_id,
                "campaign_id": s.campaign_id,
                "name": s.name,
                "status": s.status,
                "impressions": s.impressions,
                "clicks": s.clicks,
                "cost_micros": s.cost_micros,
                "conversions": s.conversions,
            }
            for s in snapshots
        ]
        stmt = insert(AdGroupSnapshotModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ad_group_snapshots",
            set_={
                "name": stmt.excluded.name,
                "status": stmt.excluded.status,
                "campaign_id": stmt.excluded.campaign_id,
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "cost_micros": stmt.excluded.cost_micros,
                "conversions": stmt.excluded.conversions,
                "updated_at": text("now()"),
            },
        )
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Keywords
    # ------------------------------------------------------------------

    async def upsert_keywords(
        self, account_id: AccountId, snapshots: list[KeywordSnapshot]
    ) -> None:
        if not snapshots:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "account_id": uuid.UUID(account_id),
                "snapshot_date": s.snapshot_date,
                "criterion_id": s.criterion_id,
                "ad_group_id": s.ad_group_id,
                "text": s.text,
                "match_type": s.match_type,
                "status": s.status,
                "quality_score": s.quality_score,
                "impressions": s.impressions,
                "clicks": s.clicks,
                "cost_micros": s.cost_micros,
                "conversions": s.conversions,
                "ctr": s.ctr,
                "avg_cpc_micros": s.avg_cpc_micros,
            }
            for s in snapshots
        ]
        stmt = insert(KeywordSnapshotModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_keyword_snapshots",
            set_={
                "text": stmt.excluded.text,
                "match_type": stmt.excluded.match_type,
                "status": stmt.excluded.status,
                "quality_score": stmt.excluded.quality_score,
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "cost_micros": stmt.excluded.cost_micros,
                "conversions": stmt.excluded.conversions,
                "ctr": stmt.excluded.ctr,
                "avg_cpc_micros": stmt.excluded.avg_cpc_micros,
                "updated_at": text("now()"),
            },
        )
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Search terms
    # ------------------------------------------------------------------

    async def upsert_search_terms(
        self, account_id: AccountId, snapshots: list[SearchTermSnapshot]
    ) -> None:
        if not snapshots:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "account_id": uuid.UUID(account_id),
                "snapshot_date": s.snapshot_date,
                "search_term": s.search_term,
                "ad_group_id": s.ad_group_id,
                "impressions": s.impressions,
                "clicks": s.clicks,
                "cost_micros": s.cost_micros,
                "conversions": s.conversions,
                "matched_keyword_id": s.matched_keyword_id,
            }
            for s in snapshots
        ]
        stmt = insert(SearchTermSnapshotModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_search_term_snapshots",
            set_={
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "cost_micros": stmt.excluded.cost_micros,
                "conversions": stmt.excluded.conversions,
                "matched_keyword_id": stmt.excluded.matched_keyword_id,
                "updated_at": text("now()"),
            },
        )
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Ads
    # ------------------------------------------------------------------

    async def upsert_ads(
        self, account_id: AccountId, snapshots: list[AdSnapshot]
    ) -> None:
        if not snapshots:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "account_id": uuid.UUID(account_id),
                "snapshot_date": s.snapshot_date,
                "ad_id": s.ad_id,
                "ad_group_id": s.ad_group_id,
                "type": s.type,
                "status": s.status,
                "headlines_json": s.headlines_json,
                "descriptions_json": s.descriptions_json,
                "final_urls_json": s.final_urls_json,
                "impressions": s.impressions,
                "clicks": s.clicks,
                "cost_micros": s.cost_micros,
                "conversions": s.conversions,
            }
            for s in snapshots
        ]
        stmt = insert(AdSnapshotModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ad_snapshots",
            set_={
                "type": stmt.excluded.type,
                "status": stmt.excluded.status,
                "headlines_json": stmt.excluded.headlines_json,
                "descriptions_json": stmt.excluded.descriptions_json,
                "final_urls_json": stmt.excluded.final_urls_json,
                "impressions": stmt.excluded.impressions,
                "clicks": stmt.excluded.clicks,
                "cost_micros": stmt.excluded.cost_micros,
                "conversions": stmt.excluded.conversions,
                "updated_at": text("now()"),
            },
        )
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def get_latest_snapshot_date(self, account_id: AccountId) -> date | None:
        result = await self._session.execute(
            select(CampaignSnapshotModel.snapshot_date)
            .where(CampaignSnapshotModel.account_id == uuid.UUID(account_id))
            .order_by(CampaignSnapshotModel.snapshot_date.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row
