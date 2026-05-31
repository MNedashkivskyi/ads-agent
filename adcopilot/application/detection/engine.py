"""Rule engine: runs rules, deduplicates, persists recommendations."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from adcopilot.application.detection.base import DetectionContext, DetectionRule
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.snooze_repository import SnoozeRepository
from adcopilot.domain.recommendation import Recommendation

logger = structlog.get_logger(__name__)


class RuleEngine:
    def __init__(
        self,
        rules: list[DetectionRule],
        rec_repo: RecommendationRepository,
        snooze_repo: SnoozeRepository | None = None,
    ) -> None:
        self._rules = rules
        self._repo = rec_repo
        self._snooze_repo = snooze_repo

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

        # 2. Load existing recs (all non-expired) for dedup — prevents re-creating
        #    recommendations the user has already acted on.
        existing_keys = await self._repo.list_active_dedup_keys(ctx.account.id)

        # 3. Load active snooze keys (kind_value, target_hash)
        snoozed_keys: set[tuple[str, str]] = set()
        if self._snooze_repo is not None:
            now = datetime.now(UTC)
            snoozed_keys = await self._snooze_repo.get_active_snooze_keys(ctx.account.id, now)

        # 4. Filter duplicates and snoozed, then persist
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
            if (rec.kind.value, rec.target_hash) in snoozed_keys:
                logger.debug(
                    "skipping snoozed recommendation",
                    kind=rec.kind.value,
                    target_hash=rec.target_hash[:8],
                )
                continue
            await self._repo.save(rec)
            existing_keys.add(key)  # prevent intra-batch dupes
            new_recs.append(rec)

        # 5. Reconcile: expire still-open PENDING recs that this run no longer
        #    detected, so the list only shows currently-actual recommendations.
        #    Guard against wiping the list on an empty/failed snapshot by
        #    requiring real campaign data in the context before reconciling.
        expired = 0
        if ctx.campaigns:
            keep_keys = {(rec.kind.value, rec.target_hash) for rec in candidates}
            expired = await self._repo.expire_pending_not_matching(ctx.account.id, keep_keys)

        logger.info(
            "rule engine completed",
            account_id=ctx.account.id,
            candidates=len(candidates),
            new=len(new_recs),
            expired_stale=expired,
        )
        return new_recs
