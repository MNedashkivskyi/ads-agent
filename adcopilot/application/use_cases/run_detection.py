"""RunDetection use case: loads snapshot, builds context, runs rule engine."""

from __future__ import annotations

from datetime import date, timedelta

import structlog

from adcopilot.application.detection.base import DetectionContext, HistoricalStats
from adcopilot.application.detection.engine import RuleEngine
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.repositories import GoogleAdsAccountRepository
from adcopilot.application.ports.snapshot_repository import SnapshotRepository
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationSeverity

logger = structlog.get_logger(__name__)

_TREND_LOOKBACK_DAYS = 7
_DEVICE_LOOKBACK_DAYS = 7
_GEO_LOOKBACK_DAYS = 30
_HOUR_LOOKBACK_DAYS = 30
_DOW_LOOKBACK_DAYS = 30


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

        # 2. Load current snapshot data
        snapshot = await self._snapshot_repo.load_snapshot(account_id, snapshot_date)

        # 3. Load 7-day-ago snapshots for trend-based rules (Modules 1 & 2).
        #    These are best-effort — if no data exists the lists stay empty and
        #    trend rules simply skip (they check for empty prev_* lists).
        prev_date = snapshot_date - timedelta(days=_TREND_LOOKBACK_DAYS)
        prev_campaigns, prev_ad_groups, prev_keywords, prev_ads = await _load_prev_snapshots(
            self._snapshot_repo, account_id, prev_date
        )

        # 3b. Load targeting dimension data for Module 4 rules (best-effort).
        (
            device_performance,
            geo_performance,
            hour_performance,
            day_of_week_performance,
            audience_performance,
        ) = await _load_targeting_performance(self._snapshot_repo, account_id, snapshot_date)

        # 4. Compute HistoricalStats from the snapshot itself (30-day proxy)
        total_cost = sum(c.cost_micros for c in snapshot.campaigns)
        total_conversions = sum(c.conversions for c in snapshot.campaigns)
        avg_cpa = int(total_cost / total_conversions) if total_conversions > 0 else 0
        history = HistoricalStats(
            avg_cpa_micros=avg_cpa,
            total_cost_micros=total_cost,
            total_conversions=total_conversions,
            days=30,
        )

        # 5. Build context
        ctx = DetectionContext(
            account=account,
            campaigns=snapshot.campaigns,
            ad_groups=snapshot.ad_groups,
            keywords=snapshot.keywords,
            search_terms=snapshot.search_terms,
            ads=snapshot.ads,
            history=history,
            snapshot_date=snapshot_date,
            prev_campaigns=prev_campaigns,
            prev_ad_groups=prev_ad_groups,
            prev_keywords=prev_keywords,
            prev_ads=prev_ads,
            negative_keywords=snapshot.negative_keywords,
            device_performance=device_performance,
            geo_performance=geo_performance,
            hour_performance=hour_performance,
            day_of_week_performance=day_of_week_performance,
            audience_performance=audience_performance,
        )

        # 6. Run rule engine
        new_recs = await self._engine.run(ctx)

        # 7. Aggregate by severity
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


async def _load_targeting_performance(
    snapshot_repo: SnapshotRepository,
    account_id: AccountId,
    snapshot_date: date,
) -> tuple[list, list, list, list, list]:
    """Load targeting dimension data for Module 4 rules (best-effort).

    Uses a 30-day window for geo/hour/day-of-week (statistical stability)
    and a 7-day window for device performance.  Returns five empty lists on
    any failure so that a missing dimension never blocks detection.
    """
    try:
        end_date = snapshot_date
        start_date_30d = snapshot_date - timedelta(days=29)
        start_date_7d = snapshot_date - timedelta(days=6)
        device = await snapshot_repo.get_device_performance(account_id, start_date_7d, end_date)
        geo = await snapshot_repo.get_geo_performance(account_id, start_date_30d, end_date)
        hour = await snapshot_repo.get_hour_performance(account_id, start_date_30d, end_date)
        dow = await snapshot_repo.get_day_of_week_performance(
            account_id, start_date_30d, end_date
        )
        audience = await snapshot_repo.get_audience_performance(account_id, snapshot_date)
        return device, geo, hour, dow, audience
    except Exception:
        return [], [], [], [], []


async def _load_prev_snapshots(
    snapshot_repo: SnapshotRepository,
    account_id: AccountId,
    prev_date: date,
) -> tuple[list, list, list, list]:
    """Load campaigns, ad groups, and keywords from prev_date.

    Returns three empty lists if no data exists for that date (new accounts,
    first run, or gap in snapshots).  Errors are swallowed so a missing
    historical snapshot never blocks the current detection run.
    """
    try:
        prev_campaigns = await snapshot_repo.get_campaigns_by_date(account_id, prev_date)
        prev_ad_groups = await snapshot_repo.get_ad_groups_by_date(account_id, prev_date)
        prev_keywords = await snapshot_repo.get_keywords_by_date(account_id, prev_date)
        prev_ads = await snapshot_repo.get_ads_by_date(account_id, prev_date)
        return prev_campaigns, prev_ad_groups, prev_keywords, prev_ads
    except Exception:
        return [], [], [], []
