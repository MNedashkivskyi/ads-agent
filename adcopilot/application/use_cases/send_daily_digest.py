"""SendDailyDigestUseCase: sends top-5 PENDING recommendations to a user via Telegram."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

import structlog

from adcopilot.application.ports.digest_sent_log_repository import DigestSentLogRepository
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.telegram_notifier import TelegramNotifier
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
    reason: str  # "sent" | "no_telegram" | "no_recommendations" | "already_sent"


class SendDailyDigestUseCase:
    def __init__(
        self,
        account_repo: object,  # GoogleAdsAccountRepository Protocol
        rec_repo: RecommendationRepository,
        digest_log_repo: DigestSentLogRepository,
        notifier: TelegramNotifier,
    ) -> None:
        self._account_repo = account_repo
        self._rec_repo = rec_repo
        self._digest_log_repo = digest_log_repo
        self._notifier = notifier

    async def execute(
        self,
        user_id: UserId,
        telegram_chat_id: int | None,
        account_ids: list[AccountId],
        today: date | None = None,
    ) -> DigestResult:
        """Send a daily digest to the user.

        Args:
            user_id: The user to send the digest to.
            telegram_chat_id: The user's Telegram chat ID (None = skip).
            account_ids: All Google Ads account IDs owned by the user.
            today: Override for the current date (for testing).
        """
        if telegram_chat_id is None:
            logger.info("skipping digest: no telegram", user_id=user_id)
            return DigestResult(sent=False, count=0, reason="no_telegram")

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

        await self._notifier.send_digest(telegram_chat_id, top_recs)

        rec_ids: list[str] = [str(rec.id) for rec in top_recs]
        await self._digest_log_repo.record(user_id, today, rec_ids)

        logger.info(
            "digest sent",
            user_id=user_id,
            chat_id=telegram_chat_id,
            count=len(top_recs),
            date=today,
        )
        return DigestResult(sent=True, count=len(top_recs), reason="sent")
