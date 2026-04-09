"""RunDetection use case: loads snapshot, builds context, runs rule engine."""

from __future__ import annotations

from datetime import date

import structlog

from adcopilot.application.detection.base import DetectionContext, HistoricalStats
from adcopilot.application.detection.engine import RuleEngine
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.repositories import GoogleAdsAccountRepository
from adcopilot.application.ports.snapshot_repository import SnapshotRepository
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationSeverity

logger = structlog.get_logger(__name__)


class RunDetectionUseCase:
    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        rec_repo: RecommendationRepository,
        rule_engine: RuleEngine,
        account_repo: GoogleAdsAccountRepository,
    ) -> None:
        self._snapshot_repo = snapshot_repo
        self._rec_repo = rec_repo
        self._engine = rule_engine
        self._account_repo = account_repo

    async def execute(self, account_id: AccountId, snapshot_date: date) -> dict[str, int]:
        """Run detection for one account on one snapshot date.

        Returns a count dict keyed by severity name, e.g. {'CRITICAL': 2, 'HIGH': 5}.
        """
        # 1. Load account entity
        account = await self._account_repo.get(account_id)
        if account is None:
            logger.warning("account not found, skipping detection", account_id=account_id)
            return {}

        # 2. Load snapshot data
        snapshot = await self._snapshot_repo.load_snapshot(account_id, snapshot_date)

        # 3. Compute HistoricalStats from the snapshot itself (30-day proxy)
        total_cost = sum(c.cost_micros for c in snapshot.campaigns)
        total_conversions = sum(c.conversions for c in snapshot.campaigns)
        avg_cpa = int(total_cost / total_conversions) if total_conversions > 0 else 0
        history = HistoricalStats(
            avg_cpa_micros=avg_cpa,
            total_cost_micros=total_cost,
            total_conversions=total_conversions,
            days=30,
        )

        # 4. Build context
        ctx = DetectionContext(
            account=account,
            campaigns=snapshot.campaigns,
            ad_groups=snapshot.ad_groups,
            keywords=snapshot.keywords,
            search_terms=snapshot.search_terms,
            ads=snapshot.ads,
            history=history,
            snapshot_date=snapshot_date,
        )

        # 5. Run rule engine
        new_recs = await self._engine.run(ctx)

        # 6. Aggregate by severity
        counts: dict[str, int] = {s.value: 0 for s in RecommendationSeverity}
        for rec in new_recs:
            counts[rec.severity.value] += 1

        logger.info(
            "detection complete",
            account_id=account_id,
            date=snapshot_date.isoformat(),
            new_recommendations=len(new_recs),
            by_severity=counts,
        )
        return counts
