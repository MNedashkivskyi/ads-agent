"""SQLAlchemy implementation of SnapshotRepository using INSERT … ON CONFLICT DO UPDATE."""

import uuid
from datetime import date

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.application.ports.snapshot_repository import SnapshotData
from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import (
    AdGroupSnapshot,
    AdSnapshot,
    CampaignSnapshot,
    KeywordSnapshot,
    NegativeKeywordSnapshot,
    SearchTermSnapshot,
    SnapshotId,
)
from adcopilot.infrastructure.db.models import (
    AdGroupSnapshotModel,
    AdSnapshotModel,
    CampaignSnapshotModel,
    KeywordSnapshotModel,
    NegativeKeywordSnapshotModel,
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
                "search_impression_share": s.search_impression_share,
                "search_budget_lost_impression_share": s.search_budget_lost_impression_share,
                "search_rank_lost_impression_share": s.search_rank_lost_impression_share,
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
                "search_impression_share": stmt.excluded.search_impression_share,
                "search_budget_lost_impression_share": stmt.excluded.search_budget_lost_impression_share,
                "search_rank_lost_impression_share": stmt.excluded.search_rank_lost_impression_share,
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
                "ad_strength": s.ad_strength,
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
                "ad_strength": stmt.excluded.ad_strength,
                "updated_at": text("now()"),
            },
        )
        await self._session.execute(stmt)

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    async def get_campaigns_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[CampaignSnapshot]:
        acct_uuid = uuid.UUID(account_id)
        res = await self._session.execute(
            select(CampaignSnapshotModel).where(
                CampaignSnapshotModel.account_id == acct_uuid,
                CampaignSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        return [
            CampaignSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                campaign_id=m.campaign_id,
                name=m.name,
                status=m.status,
                channel_type=m.channel_type,
                budget_micros=m.budget_micros,
                bidding_strategy=m.bidding_strategy,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
                conv_value=m.conv_value,
                search_impression_share=m.search_impression_share,
                search_budget_lost_impression_share=m.search_budget_lost_impression_share,
                search_rank_lost_impression_share=m.search_rank_lost_impression_share,
            )
            for m in res.scalars().all()
        ]

    async def get_ad_groups_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[AdGroupSnapshot]:
        acct_uuid = uuid.UUID(account_id)
        res = await self._session.execute(
            select(AdGroupSnapshotModel).where(
                AdGroupSnapshotModel.account_id == acct_uuid,
                AdGroupSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        return [
            AdGroupSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                ad_group_id=m.ad_group_id,
                campaign_id=m.campaign_id,
                name=m.name,
                status=m.status,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
            )
            for m in res.scalars().all()
        ]

    async def get_keywords_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[KeywordSnapshot]:
        acct_uuid = uuid.UUID(account_id)
        res = await self._session.execute(
            select(KeywordSnapshotModel).where(
                KeywordSnapshotModel.account_id == acct_uuid,
                KeywordSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        return [
            KeywordSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                criterion_id=m.criterion_id,
                ad_group_id=m.ad_group_id,
                text=m.text,
                match_type=m.match_type,
                status=m.status,
                quality_score=m.quality_score,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
                ctr=m.ctr,
                avg_cpc_micros=m.avg_cpc_micros,
            )
            for m in res.scalars().all()
        ]

    async def get_ads_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[AdSnapshot]:
        acct_uuid = uuid.UUID(account_id)
        res = await self._session.execute(
            select(AdSnapshotModel).where(
                AdSnapshotModel.account_id == acct_uuid,
                AdSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        return [
            AdSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                ad_id=m.ad_id,
                ad_group_id=m.ad_group_id,
                type=m.type,
                status=m.status,
                headlines_json=m.headlines_json,
                descriptions_json=m.descriptions_json,
                final_urls_json=m.final_urls_json,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
                ad_strength=m.ad_strength,
            )
            for m in res.scalars().all()
        ]

    # ------------------------------------------------------------------
    # Negative keywords
    # ------------------------------------------------------------------

    async def upsert_negative_keywords(
        self, account_id: AccountId, snapshots: list[NegativeKeywordSnapshot]
    ) -> None:
        if not snapshots:
            return
        rows = [
            {
                "id": uuid.uuid4(),
                "account_id": uuid.UUID(account_id),
                "snapshot_date": s.snapshot_date,
                "criterion_id": s.criterion_id,
                "campaign_id": s.campaign_id,
                "ad_group_id": s.ad_group_id,
                "text": s.text,
                "match_type": s.match_type,
            }
            for s in snapshots
        ]
        stmt = insert(NegativeKeywordSnapshotModel).values(rows)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_negative_keyword_snapshots",
            set_={
                "text": stmt.excluded.text,
                "match_type": stmt.excluded.match_type,
                "updated_at": text("now()"),
            },
        )
        await self._session.execute(stmt)

    async def get_negative_keywords_by_date(
        self, account_id: AccountId, snapshot_date: date
    ) -> list[NegativeKeywordSnapshot]:
        acct_uuid = uuid.UUID(account_id)
        res = await self._session.execute(
            select(NegativeKeywordSnapshotModel).where(
                NegativeKeywordSnapshotModel.account_id == acct_uuid,
                NegativeKeywordSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        return [
            NegativeKeywordSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                criterion_id=m.criterion_id,
                campaign_id=m.campaign_id,
                ad_group_id=m.ad_group_id,
                text=m.text,
                match_type=m.match_type,
            )
            for m in res.scalars().all()
        ]

    async def get_latest_snapshot_date(self, account_id: AccountId) -> date | None:
        result = await self._session.execute(
            select(CampaignSnapshotModel.snapshot_date)
            .where(CampaignSnapshotModel.account_id == uuid.UUID(account_id))
            .order_by(CampaignSnapshotModel.snapshot_date.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return row

    async def load_snapshot(self, account_id: AccountId, snapshot_date: date) -> SnapshotData:
        """Load all five collections for an account on a given date."""
        acct_uuid = uuid.UUID(account_id)

        campaigns_res = await self._session.execute(
            select(CampaignSnapshotModel).where(
                CampaignSnapshotModel.account_id == acct_uuid,
                CampaignSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        campaigns = [
            CampaignSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                campaign_id=m.campaign_id,
                name=m.name,
                status=m.status,
                channel_type=m.channel_type,
                budget_micros=m.budget_micros,
                bidding_strategy=m.bidding_strategy,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
                conv_value=m.conv_value,
                search_impression_share=m.search_impression_share,
                search_budget_lost_impression_share=m.search_budget_lost_impression_share,
                search_rank_lost_impression_share=m.search_rank_lost_impression_share,
            )
            for m in campaigns_res.scalars().all()
        ]

        ag_res = await self._session.execute(
            select(AdGroupSnapshotModel).where(
                AdGroupSnapshotModel.account_id == acct_uuid,
                AdGroupSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        ad_groups = [
            AdGroupSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                ad_group_id=m.ad_group_id,
                campaign_id=m.campaign_id,
                name=m.name,
                status=m.status,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
            )
            for m in ag_res.scalars().all()
        ]

        kw_res = await self._session.execute(
            select(KeywordSnapshotModel).where(
                KeywordSnapshotModel.account_id == acct_uuid,
                KeywordSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        keywords = [
            KeywordSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                criterion_id=m.criterion_id,
                ad_group_id=m.ad_group_id,
                text=m.text,
                match_type=m.match_type,
                status=m.status,
                quality_score=m.quality_score,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
                ctr=m.ctr,
                avg_cpc_micros=m.avg_cpc_micros,
            )
            for m in kw_res.scalars().all()
        ]

        st_res = await self._session.execute(
            select(SearchTermSnapshotModel).where(
                SearchTermSnapshotModel.account_id == acct_uuid,
                SearchTermSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        search_terms = [
            SearchTermSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                search_term=m.search_term,
                ad_group_id=m.ad_group_id,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
                matched_keyword_id=m.matched_keyword_id,
            )
            for m in st_res.scalars().all()
        ]

        ad_res = await self._session.execute(
            select(AdSnapshotModel).where(
                AdSnapshotModel.account_id == acct_uuid,
                AdSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        ads = [
            AdSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                ad_id=m.ad_id,
                ad_group_id=m.ad_group_id,
                type=m.type,
                status=m.status,
                headlines_json=m.headlines_json,
                descriptions_json=m.descriptions_json,
                final_urls_json=m.final_urls_json,
                impressions=m.impressions,
                clicks=m.clicks,
                cost_micros=m.cost_micros,
                conversions=m.conversions,
                ad_strength=m.ad_strength,
            )
            for m in ad_res.scalars().all()
        ]

        neg_res = await self._session.execute(
            select(NegativeKeywordSnapshotModel).where(
                NegativeKeywordSnapshotModel.account_id == acct_uuid,
                NegativeKeywordSnapshotModel.snapshot_date == snapshot_date,
            )
        )
        negative_keywords = [
            NegativeKeywordSnapshot(
                id=SnapshotId(str(m.id)),
                account_id=account_id,
                snapshot_date=m.snapshot_date,
                criterion_id=m.criterion_id,
                campaign_id=m.campaign_id,
                ad_group_id=m.ad_group_id,
                text=m.text,
                match_type=m.match_type,
            )
            for m in neg_res.scalars().all()
        ]

        return SnapshotData(
            campaigns=campaigns,
            ad_groups=ad_groups,
            keywords=keywords,
            search_terms=search_terms,
            ads=ads,
            negative_keywords=negative_keywords,
        )
