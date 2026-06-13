"""generate_keyword_candidates — wide-net, intent-anchored generation.

Allocate candidate slots across the keyword-intent dimension (uniform now,
learned later), ask the LLM for candidates per intent-type, tag each with its
intent, and persist as ``generated``. Harvested winning terms (Phase 5) are fed
in as extra seed material, deduped and capped.
"""

from __future__ import annotations

import structlog

from adcopilot.application.ports.cie_keyword_repository import CieKeywordRepository
from adcopilot.application.ports.keyword_generator import KeywordGeneratorPort
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import KeywordCandidate
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.value_objects import KeywordIntent
from adcopilot.domain.campaign_intelligence.shared import dimension_selector
from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    DimensionPerformance,
)
from adcopilot.domain.exceptions import LLMError

logger = structlog.get_logger(__name__)

DEFAULT_TOTAL_SLOTS = 30
MAX_SEEDS = 25

_INTENT_VALUES = [i.value for i in KeywordIntent]


class GenerateKeywordCandidatesUseCase:
    def __init__(
        self,
        generator: KeywordGeneratorPort,
        repo: CieKeywordRepository,
    ) -> None:
        self._generator = generator
        self._repo = repo

    async def run(
        self,
        run: KeywordRun,
        *,
        total_slots: int = DEFAULT_TOTAL_SLOTS,
        learned_performance: dict[str, DimensionPerformance] | None = None,
    ) -> KeywordRun:
        if run.id is None:
            raise ValueError("run must be persisted (id set) before generation")

        allocation = dimension_selector.allocate(
            total_slots, _INTENT_VALUES, learned_performance or {}
        )
        logger.info(
            "cie.keywords.generate",
            run_id=run.id,
            vertical=run.vertical,
            allocation=allocation,
        )

        problems = self._merge_seeds(run.problems, run.seeds)
        try:
            generated = await self._generator.generate(
                service=run.service,
                vertical=run.vertical,
                problems=problems,
                intent_allocation=allocation,
                language=run.language,
            )
        except LLMError as exc:
            await self._repo.set_run_status(run.id, KeywordRunStatus.FAILED, str(exc))
            run.status = KeywordRunStatus.FAILED
            run.error = str(exc)
            raise

        candidates = [
            KeywordCandidate(
                phrase=g.phrase,
                intent=KeywordIntent(g.intent),
                reasoning=g.reasoning,
                source="llm",
            )
            for g in generated
        ]
        await self._repo.replace_candidates(run.id, run.campaign_id, candidates)
        await self._repo.set_run_status(run.id, KeywordRunStatus.GENERATED)
        run.status = KeywordRunStatus.GENERATED
        logger.info("cie.keywords.generated", run_id=run.id, count=len(candidates))
        return run

    @staticmethod
    def _merge_seeds(problems: list[str], seeds: list[str]) -> list[str]:
        """Append harvested seeds to the problem material, deduped and capped."""
        merged = list(problems)
        seen = {p.strip().lower() for p in problems}
        for seed in seeds[:MAX_SEEDS]:
            key = seed.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(f"(sprawdzone hasło) {seed}")
        return merged
