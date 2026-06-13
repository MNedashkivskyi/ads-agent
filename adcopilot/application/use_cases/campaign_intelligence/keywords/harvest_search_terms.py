"""harvest_search_terms — close the keyword loop from reality.

Reads the search-term facts ingested in Phase 4, promotes the real converting
queries that aren't yet keywords, flags wasteful ones as negatives, and persists
both lists for one-click adoption. Idempotent — re-running doesn't duplicate prior
proposals.
"""

from __future__ import annotations

import structlog

from adcopilot.application.ports.cie_performance import (
    CieAttributionRepository,
    CiePerformanceFactRepository,
)
from adcopilot.application.ports.cie_search_term_repository import CieSearchTermRepository
from adcopilot.domain.campaign_intelligence.keywords.search_term import (
    HarvestResult,
    SearchTerm,
    harvest,
)

logger = structlog.get_logger(__name__)


class HarvestSearchTermsUseCase:
    def __init__(
        self,
        fact_repo: CiePerformanceFactRepository,
        attribution_repo: CieAttributionRepository,
        proposal_repo: CieSearchTermRepository,
    ) -> None:
        self._facts = fact_repo
        self._attribution = attribution_repo
        self._proposals = proposal_repo

    async def run(
        self,
        *,
        account_id: str,
        customer_id: str,
        vertical: str,
        language: str,
    ) -> HarvestResult:
        facts = await self._facts.list_search_term_facts(account_id)
        existing = set((await self._attribution.keyword_intent_map(account_id)).keys())

        terms = [
            SearchTerm(
                term=(f.extra or {}).get("search_term", ""),
                matched_keyword=(f.extra or {}).get("matched_keyword", ""),
                impressions=f.impressions,
                clicks=f.clicks,
                conversions=f.conversions,
                cost_micros=f.cost_micros,
                intent=f.value,
            )
            for f in facts
            if (f.extra or {}).get("search_term")
        ]

        result = harvest(terms, existing)
        await self._proposals.save_proposals(
            account_id=account_id,
            customer_id=customer_id,
            campaign_id=None,
            vertical=vertical,
            language=language,
            proposals=result.promotions + result.negatives,
        )
        logger.info(
            "cie.harvest",
            account_id=account_id,
            promotions=len(result.promotions),
            negatives=len(result.negatives),
        )
        return result
