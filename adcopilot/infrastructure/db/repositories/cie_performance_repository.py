"""SQL implementations of the CIE attribution + performance-fact repositories."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.application.ports.cie_performance import (
    DimensionAggregate,
    PerformanceFact,
)
from adcopilot.infrastructure.db.models import (
    CieAdsPerformanceFactModel,
    CieHookCandidateModel,
    CieHookSetModel,
    CieKeywordCandidateModel,
    CieKeywordRunModel,
    CieShippedAssetModel,
    CieShippedKeywordModel,
)


class SqlCieAttributionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def keyword_intent_map(self, account_id: str) -> dict[str, str]:
        acct = uuid.UUID(account_id)
        out: dict[str, str] = {}
        # Validated candidates (joined to runs for this account) provide the base.
        rows = await self._session.execute(
            select(CieKeywordCandidateModel.phrase, CieKeywordCandidateModel.intent)
            .join(CieKeywordRunModel, CieKeywordRunModel.id == CieKeywordCandidateModel.run_id)
            .where(CieKeywordRunModel.account_id == acct)
        )
        for phrase, intent in rows.all():
            out[phrase.strip().lower()] = intent
        # Explicitly shipped keywords take precedence.
        shipped = await self._session.execute(
            select(CieShippedKeywordModel.keyword_text, CieShippedKeywordModel.intent).where(
                CieShippedKeywordModel.account_id == acct
            )
        )
        for text, intent in shipped.all():
            out[text.strip().lower()] = intent
        return out

    async def asset_angle_map(self, account_id: str) -> dict[str, str]:
        acct = uuid.UUID(account_id)
        out: dict[str, str] = {}
        rows = await self._session.execute(
            select(CieHookCandidateModel.text, CieHookCandidateModel.angle)
            .join(CieHookSetModel, CieHookSetModel.id == CieHookCandidateModel.set_id)
            .where(CieHookSetModel.account_id == acct)
        )
        for text, angle in rows.all():
            out[text.strip().lower()] = angle
        shipped = await self._session.execute(
            select(CieShippedAssetModel.asset_text, CieShippedAssetModel.angle).where(
                CieShippedAssetModel.account_id == acct
            )
        )
        for text, angle in shipped.all():
            out[text.strip().lower()] = angle
        return out


class SqlCiePerformanceFactRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_facts(self, facts: list[PerformanceFact]) -> int:
        written = 0
        for f in facts:
            stmt = pg_insert(CieAdsPerformanceFactModel).values(
                account_id=uuid.UUID(f.account_id),
                customer_id=f.customer_id,
                entity_type=f.entity_type,
                entity_id=f.entity_id,
                day=f.day,
                dimension=f.dimension,
                value=f.value,
                vertical=f.vertical,
                language=f.language,
                impressions=f.impressions,
                clicks=f.clicks,
                conversions=f.conversions,
                cost_micros=f.cost_micros,
                performance_label=f.performance_label,
                extra=f.extra,
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_cie_perf_fact",
                set_={
                    "dimension": stmt.excluded.dimension,
                    "value": stmt.excluded.value,
                    "impressions": stmt.excluded.impressions,
                    "clicks": stmt.excluded.clicks,
                    "conversions": stmt.excluded.conversions,
                    "cost_micros": stmt.excluded.cost_micros,
                    "performance_label": stmt.excluded.performance_label,
                    "extra": stmt.excluded.extra,
                    "updated_at": func.now(),
                },
            )
            await self._session.execute(stmt)
            written += 1
        return written

    async def aggregate_by_dimension(self, dimension: str) -> list[DimensionAggregate]:
        m = CieAdsPerformanceFactModel
        rows = await self._session.execute(
            select(
                m.vertical,
                m.value,
                m.language,
                func.sum(m.impressions),
                func.sum(m.clicks),
                func.sum(m.conversions),
            )
            .where(m.dimension == dimension, m.value.is_not(None))
            .group_by(m.vertical, m.value, m.language)
        )
        return [
            DimensionAggregate(
                vertical=vertical,
                dimension=dimension,
                value=value,
                language=language,
                impressions=int(impr or 0),
                clicks=int(clicks or 0),
                conversions=float(conv or 0.0),
            )
            for vertical, value, language, impr, clicks, conv in rows.all()
        ]

    async def list_search_term_facts(self, account_id: str) -> list[PerformanceFact]:
        m = CieAdsPerformanceFactModel
        rows = await self._session.execute(
            select(m).where(
                m.account_id == uuid.UUID(account_id), m.entity_type == "search_term"
            )
        )
        return [_fact_to_domain(r) for r in rows.scalars().all()]


def _fact_to_domain(m: CieAdsPerformanceFactModel) -> PerformanceFact:
    return PerformanceFact(
        account_id=str(m.account_id),
        customer_id=m.customer_id,
        entity_type=m.entity_type,
        entity_id=m.entity_id,
        day=m.day,
        dimension=m.dimension,
        value=m.value,
        vertical=m.vertical,
        language=m.language,
        impressions=m.impressions,
        clicks=m.clicks,
        conversions=m.conversions,
        cost_micros=m.cost_micros,
        performance_label=m.performance_label,
        extra=m.extra,
    )
