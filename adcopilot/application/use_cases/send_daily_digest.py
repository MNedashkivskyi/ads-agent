"""SendDailyDigestUseCase: computes top-5 PENDING recommendations and logs them (log-only mode)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import structlog

from adcopilot.application.ports.digest_sent_log_repository import DigestSentLogRepository
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.domain.entities import AccountId, UserId
from adcopilot.domain.recommendation import Recommendation, RecommendationSeverity

logger = structlog.get_logger(__name__)

_SEVERITY_ORDER = {
    RecommendationSeverity.CRITICAL: 0,
    RecommendationSeverity.HIGH: 1,
    RecommendationSeverity.MEDIUM: 2,
    RecommendationSeverity.LOW: 3,
}

_MAX_RECS = 5


def _sort_key(rec: Recommendation) -> tuple[int, int]:
    return (_SEVERITY_ORDER[rec.severity], -rec.estimated_monthly_savings_micros)


@dataclass
class DigestResult:
    sent: bool
    count: int
    reason: str  # "sent" | "no_recommendations" | "already_sent"


class SendDailyDigestUseCase:
    def __init__(
        self,
        account_repo: object,  # GoogleAdsAccountRepository Protocol
        rec_repo: RecommendationRepository,
        digest_log_repo: DigestSentLogRepository,
    ) -> None:
        self._account_repo = account_repo
        self._rec_repo = rec_repo
        self._digest_log_repo = digest_log_repo

    async def execute(
        self,
        user_id: UserId,
        account_ids: list[AccountId],
        today: date | None = None,
        notifications_paused: bool = False,
    ) -> DigestResult:
        """Compute and log the daily digest for a user (log-only; no notification sent yet).

        Args:
            user_id: The user to compute the digest for.
            account_ids: All Google Ads account IDs owned by the user.
            today: Override for the current date (for testing).
            notifications_paused: If True, skip this user's digest.
        """
        if notifications_paused:
            logger.info("skipping digest: notifications paused", user_id=user_id)
            return DigestResult(sent=False, count=0, reason="paused")

        today = today or datetime.now(UTC).date()

        if await self._digest_log_repo.was_sent_today(user_id, today):
            logger.info("skipping digest: already sent today", user_id=user_id, date=today)
            return DigestResult(sent=False, count=0, reason="already_sent")

        # Collect PENDING recommendations from all accounts
        all_recs: list[Recommendation] = []
        for account_id in account_ids:
            recs = await self._rec_repo.list_pending(account_id)
            all_recs.extend(recs)

        if not all_recs:
            logger.info("skipping digest: no recommendations", user_id=user_id)
            return DigestResult(sent=False, count=0, reason="no_recommendations")

        top_recs = sorted(all_recs, key=_sort_key)[:_MAX_RECS]

        rec_ids: list[str] = [str(rec.id) for rec in top_recs]
        await self._digest_log_repo.record(user_id, today, rec_ids)

        logger.info(
            "digest computed (log-only)",
            user_id=user_id,
            count=len(top_recs),
            date=today,
        )
        return DigestResult(sent=True, count=len(top_recs), reason="sent")
