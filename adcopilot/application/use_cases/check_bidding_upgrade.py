"""CheckBiddingUpgradeUseCase: detect campaigns eligible for a bidding strategy upgrade.

Logic
-----
For each ENABLED campaign on the account's latest snapshot:

- MAXIMIZE_CLICKS with ≥ 30 conversions in the last 30 days
  → recommend upgrade to MAXIMIZE_CONVERSIONS

- MAXIMIZE_CONVERSIONS with ≥ 50 conversions and no TARGET_CPA set
  → recommend upgrade to TARGET_CPA (target = 75 % of account avg CPA)

Duplicate recommendations are suppressed: if a PENDING
ADJUST_BIDDING_STRATEGY recommendation already exists for the same
campaign the rule is skipped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.snapshot_repository import SnapshotRepository
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

logger = structlog.get_logger(__name__)

_MAXIMIZE_CLICKS_UPGRADE_THRESHOLD = 30   # conversions/30 days
_MAXIMIZE_CONV_UPGRADE_THRESHOLD = 50     # conversions/30 days
_TARGET_CPA_RATIO = 0.75                  # 75 % of account avg CPA


class CheckBiddingUpgradeUseCase:
    """For each active campaign, check if conversion volume warrants a bidding upgrade."""

    def __init__(
        self,
        snapshot_repo: SnapshotRepository,
        rec_repo: RecommendationRepository,
    ) -> None:
        self._snapshot_repo = snapshot_repo
        self._rec_repo = rec_repo

    async def execute(self, account_id: AccountId) -> list[Recommendation]:
        """Check all ENABLED campaigns and return newly created recommendations."""
        latest_date = await self._snapshot_repo.get_latest_snapshot_date(account_id)
        if latest_date is None:
            logger.info("no snapshot data, skipping bidding upgrade check", account_id=account_id)
            return []

        campaigns = await self._snapshot_repo.get_campaigns_by_date(account_id, latest_date)
        pending = await self._rec_repo.list_pending(account_id)

        # Build a set of campaign_ids that already have a pending bidding recommendation
        pending_campaign_ids: set[int] = {
            int(r.payload["campaign_id"])
            for r in pending
            if r.kind == RecommendationKind.ADJUST_BIDDING_STRATEGY
            and "campaign_id" in r.payload
        }

        # Sum conversions across all snapshots in last 30 days for each campaign
        # (We use the latest snapshot as a proxy — it contains 30-day cumulative
        # conversions as tracked by the nightly snapshot job.)
        new_recs: list[Recommendation] = []

        # Compute account-level avg CPA for TARGET_CPA baseline
        total_cost = sum(c.cost_micros for c in campaigns if c.status == "ENABLED")
        total_conv = sum(c.conversions for c in campaigns if c.status == "ENABLED")
        avg_cpa_micros = int((total_cost / total_conv) * _TARGET_CPA_RATIO) if total_conv > 0 else 0

        for campaign in campaigns:
            if campaign.status != "ENABLED":
                continue
            if campaign.campaign_id in pending_campaign_ids:
                continue

            strategy = campaign.bidding_strategy
            conversions = campaign.conversions

            rec: Recommendation | None = None

            if strategy == "MAXIMIZE_CLICKS" and conversions >= _MAXIMIZE_CLICKS_UPGRADE_THRESHOLD:
                rec = Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=account_id,
                    kind=RecommendationKind.ADJUST_BIDDING_STRATEGY,
                    severity=RecommendationSeverity.HIGH,
                    status=RecommendationStatus.PENDING,
                    target={"campaign_id": campaign.campaign_id},
                    payload={
                        "campaign_id": campaign.campaign_id,
                        "campaign_name": campaign.name,
                        "current_strategy": "MAXIMIZE_CLICKS",
                        "suggested_strategy": "MAXIMIZE_CONVERSIONS",
                        "conversions_30d": conversions,
                        "reason": "upgrade_threshold_reached",
                    },
                    estimated_monthly_savings_micros=0,
                    evidence={"conversions_30d": conversions},
                    created_at=datetime.now(UTC),
                )

            elif (
                strategy == "MAXIMIZE_CONVERSIONS"
                and conversions >= _MAXIMIZE_CONV_UPGRADE_THRESHOLD
                and campaign.target_cpa_micros is None
            ):
                rec = Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=account_id,
                    kind=RecommendationKind.ADJUST_BIDDING_STRATEGY,
                    severity=RecommendationSeverity.HIGH,
                    status=RecommendationStatus.PENDING,
                    target={"campaign_id": campaign.campaign_id},
                    payload={
                        "campaign_id": campaign.campaign_id,
                        "campaign_name": campaign.name,
                        "current_strategy": "MAXIMIZE_CONVERSIONS",
                        "suggested_strategy": "TARGET_CPA",
                        "target_cpa_micros": avg_cpa_micros,
                        "conversions_30d": conversions,
                        "reason": "upgrade_threshold_reached",
                    },
                    estimated_monthly_savings_micros=0,
                    evidence={"conversions_30d": conversions, "avg_cpa_micros": avg_cpa_micros},
                    created_at=datetime.now(UTC),
                )

            if rec is not None:
                await self._rec_repo.save(rec)
                new_recs.append(rec)
                logger.info(
                    "bidding upgrade recommendation created",
                    account_id=account_id,
                    campaign_id=campaign.campaign_id,
                    current=strategy,
                    suggested=rec.payload["suggested_strategy"],
                )

        return new_recs
