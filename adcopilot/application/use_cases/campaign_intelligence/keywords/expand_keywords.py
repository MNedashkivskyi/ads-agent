"""expand_keywords — reality-grounded expansion of strong INTENT seeds.

Feeds the top INTENT seeds into DataForSEO "Keywords for Keywords" to surface
high-volume phrasings the LLM wouldn't invent, deduped against what the campaign
already has, and appended as ``generated`` candidates so the next validation pass
prices them. Gated behind a feature flag and a per-request cost ceiling.
"""

from __future__ import annotations

import structlog

from adcopilot.application.ports.cie_keyword_repository import CieKeywordRepository
from adcopilot.application.ports.keyword_expander import KeywordExpanderPort
from adcopilot.application.ports.keyword_volume import VolumeRequestContext
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import KeywordCandidate
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import KeywordRun
from adcopilot.domain.campaign_intelligence.keywords.value_objects import KeywordIntent

logger = structlog.get_logger(__name__)

DEFAULT_TOP_K = 5


class ExpandKeywordsUseCase:
    def __init__(
        self,
        expander: KeywordExpanderPort,
        repo: CieKeywordRepository,
        *,
        enabled: bool,
        max_requests: int,
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._expander = expander
        self._repo = repo
        self._enabled = enabled
        self._max_requests = max_requests
        self._top_k = top_k

    async def run(self, run: KeywordRun) -> list[KeywordCandidate]:
        if run.id is None:
            raise ValueError("run must be persisted before expansion")
        if not self._enabled or not getattr(self._expander, "is_configured", False):
            logger.info("cie.keywords.expand.disabled", run_id=run.id)
            return []

        seeds = await self._top_intent_seeds(run.id)
        if not seeds:
            return []

        ctx = VolumeRequestContext(geo="PL", language=run.language)
        expanded = await self._expander.expand_keywords(
            seeds, ctx, max_requests=self._max_requests
        )

        existing = await self._repo.list_phrases_for_campaign(run.campaign_id)
        added: list[KeywordCandidate] = []
        seen = set(existing)
        for g in expanded:
            key = g.phrase.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            added.append(
                KeywordCandidate(
                    phrase=g.phrase,
                    intent=KeywordIntent.INTENT,
                    reasoning=g.reasoning or "expansion",
                    source="expansion",
                )
            )

        if added:
            await self._repo.add_candidates(run.id, run.campaign_id, added)
        logger.info(
            "cie.keywords.expanded", run_id=run.id, seeds=len(seeds), added=len(added)
        )
        return added

    async def _top_intent_seeds(self, run_id: str) -> list[str]:
        candidates = await self._repo.list_candidates(run_id)
        intent_candidates = [c for c in candidates if c.intent is KeywordIntent.INTENT]
        # Prefer validated, higher-volume seeds; fall back to generation order.
        intent_candidates.sort(
            key=lambda c: (c.volume.monthly_searches if c.volume else 0),
            reverse=True,
        )
        return [c.phrase for c in intent_candidates[: self._top_k]]
