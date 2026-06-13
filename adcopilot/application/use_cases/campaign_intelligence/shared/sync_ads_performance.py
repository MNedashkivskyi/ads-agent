"""sync_ads_performance — ONE ingest, both tracks.

Pulls per-asset, per-keyword, and search-term performance for an account in a
single pass and attributes each row back to its strategic-dimension value:
assets → ``angle``, keywords → ``intent-type``. Search-term rows are stored
attributed-by-matched-keyword for the harvesting loop. Writes idempotent facts
keyed by (entity, day) so re-running a day never duplicates.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date

import structlog

from adcopilot.application.ports.ads_performance import AdsPerformancePort
from adcopilot.application.ports.cie_performance import (
    CieAttributionRepository,
    CiePerformanceFactRepository,
    PerformanceFact,
)
from adcopilot.domain.campaign_intelligence.creatives.angle import ANGLE_DIMENSION
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KEYWORD_INTENT_DIMENSION,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SyncResult:
    assets: int
    keywords: int
    search_terms: int
    facts_written: int


class SyncAdsPerformanceUseCase:
    def __init__(
        self,
        perf_port: AdsPerformancePort,
        attribution_repo: CieAttributionRepository,
        fact_repo: CiePerformanceFactRepository,
    ) -> None:
        self._perf = perf_port
        self._attribution = attribution_repo
        self._facts = fact_repo

    async def run(
        self,
        *,
        account_id: str,
        customer_id: str,
        refresh_token: str,
        vertical: str,
        language: str,
        start_date: date,
        end_date: date,
    ) -> SyncResult:
        assets = await self._perf.fetch_asset_performance(
            refresh_token, customer_id, start_date=start_date, end_date=end_date
        )
        keywords = await self._perf.fetch_keyword_performance(
            refresh_token, customer_id, start_date=start_date, end_date=end_date
        )
        search_terms = await self._perf.fetch_search_terms(
            refresh_token, customer_id, start_date=start_date, end_date=end_date
        )

        angle_map = await self._attribution.asset_angle_map(account_id)
        intent_map = await self._attribution.keyword_intent_map(account_id)

        facts: list[PerformanceFact] = []
        for a in assets:
            facts.append(
                PerformanceFact(
                    account_id=account_id,
                    customer_id=customer_id,
                    entity_type="asset",
                    entity_id=a.asset_id,
                    day=a.day,
                    dimension=ANGLE_DIMENSION,
                    value=angle_map.get(a.asset_text.strip().lower()),
                    vertical=vertical,
                    language=language,
                    impressions=a.impressions,
                    clicks=a.clicks,
                    conversions=a.conversions,
                    cost_micros=a.cost_micros,
                    performance_label=a.performance_label,
                    extra={"text": a.asset_text, "surface": a.field_type},
                )
            )
        for k in keywords:
            facts.append(
                PerformanceFact(
                    account_id=account_id,
                    customer_id=customer_id,
                    entity_type="keyword",
                    entity_id=k.criterion_id,
                    day=k.day,
                    dimension=KEYWORD_INTENT_DIMENSION,
                    value=intent_map.get(k.keyword_text.strip().lower()),
                    vertical=vertical,
                    language=language,
                    impressions=k.impressions,
                    clicks=k.clicks,
                    conversions=k.conversions,
                    cost_micros=k.cost_micros,
                    extra={"text": k.keyword_text, "match_type": k.match_type},
                )
            )
        for s in search_terms:
            facts.append(
                PerformanceFact(
                    account_id=account_id,
                    customer_id=customer_id,
                    entity_type="search_term",
                    entity_id=_term_id(s.campaign_id, s.ad_group_id, s.search_term),
                    day=s.day,
                    dimension=KEYWORD_INTENT_DIMENSION,
                    value=intent_map.get(s.matched_keyword_text.strip().lower()),
                    vertical=vertical,
                    language=language,
                    impressions=s.impressions,
                    clicks=s.clicks,
                    conversions=s.conversions,
                    cost_micros=s.cost_micros,
                    extra={
                        "search_term": s.search_term,
                        "matched_keyword": s.matched_keyword_text,
                        "status": s.status,
                    },
                )
            )

        written = await self._facts.upsert_facts(facts)
        result = SyncResult(
            assets=len(assets),
            keywords=len(keywords),
            search_terms=len(search_terms),
            facts_written=written,
        )
        logger.info("cie.sync_performance", account_id=account_id, **result.__dict__)
        return result


def _term_id(campaign_id: str, ad_group_id: str, term: str) -> str:
    digest = hashlib.sha1(f"{campaign_id}:{ad_group_id}:{term}".encode()).hexdigest()
    return f"st_{digest[:24]}"
