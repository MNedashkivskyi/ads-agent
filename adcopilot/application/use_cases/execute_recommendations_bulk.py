"""BulkExecuteRecommendationsUseCase — execute many recommendations in one call.

Agency-scale convenience: approve/run a batch of recommendations at once. Each
is run through the existing per-recommendation use case (which resolves its own
account + credentials and enforces the spend-safety guard), so this layer only
adds iteration with **per-item failure isolation** — one bad recommendation
never sinks the rest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import structlog

from adcopilot.domain.recommendation import RecommendationId

logger = structlog.get_logger(__name__)


class _SingleExecutor(Protocol):
    async def execute(self, rec_id: RecommendationId) -> dict[str, Any]: ...


@dataclass
class BulkExecutionResult:
    total: int
    succeeded: int
    failed: int
    results: list[dict[str, Any]] = field(default_factory=list)


class BulkExecuteRecommendationsUseCase:
    def __init__(self, single: _SingleExecutor) -> None:
        # `single` runs one recommendation in its own session/transaction, so a
        # failure never poisons sibling items.
        self._single = single

    async def execute(self, rec_ids: list[RecommendationId]) -> BulkExecutionResult:
        results: list[dict[str, Any]] = []
        for rec_id in rec_ids:
            try:
                outcome = await self._single.execute(rec_id)
                results.append({"recommendation_id": str(rec_id), "ok": True, "result": outcome})
            except Exception as exc:  # isolate — keep going
                logger.warning(
                    "bulk_execute_item_failed",
                    recommendation_id=str(rec_id),
                    error=str(exc)[:200],
                )
                results.append(
                    {"recommendation_id": str(rec_id), "ok": False, "error": str(exc)[:200]}
                )

        succeeded = sum(1 for r in results if r["ok"])
        return BulkExecutionResult(
            total=len(rec_ids),
            succeeded=succeeded,
            failed=len(rec_ids) - succeeded,
            results=results,
        )
