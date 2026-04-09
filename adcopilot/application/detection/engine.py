"""Rule engine: runs rules, deduplicates, persists recommendations."""

from __future__ import annotations

import structlog

from adcopilot.application.detection.base import DetectionContext, DetectionRule
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.domain.recommendation import Recommendation

logger = structlog.get_logger(__name__)


class RuleEngine:
    def __init__(
        self,
        rules: list[DetectionRule],
        rec_repo: RecommendationRepository,
    ) -> None:
        self._rules = rules
        self._repo = rec_repo

    async def run(self, ctx: DetectionContext) -> list[Recommendation]:
        """Run all rules, deduplicate against existing PENDING, persist new ones."""
        # 1. Collect all candidates
        candidates: list[Recommendation] = []
        for rule in self._rules:
            try:
                found = rule.detect(ctx)
                candidates.extend(found)
            except Exception:
                logger.exception("rule raised unexpectedly", rule=type(rule).__name__)

        # 2. Load existing PENDING for dedup
        existing = await self._repo.list_pending(ctx.account.id)
        existing_keys = {(r.kind, r.target_hash) for r in existing}

        # 3. Filter duplicates and persist
        new_recs: list[Recommendation] = []
        for rec in candidates:
            key = (rec.kind, rec.target_hash)
            if key in existing_keys:
                logger.debug(
                    "skipping duplicate recommendation",
                    kind=rec.kind.value,
                    target_hash=rec.target_hash[:8],
                )
                continue
            await self._repo.save(rec)
            existing_keys.add(key)  # prevent intra-batch dupes
            new_recs.append(rec)

        logger.info(
            "rule engine completed",
            account_id=ctx.account.id,
            candidates=len(candidates),
            new=len(new_recs),
        )
        return new_recs
