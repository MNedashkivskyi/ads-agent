"""ExecuteRecommendationUseCase: runs the Google Ads mutation for an approved recommendation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from adcopilot.application.ports.audit_log_repository import AuditLogRepository
from adcopilot.application.ports.google_ads_mutations import GoogleAdsMutationsPort
from adcopilot.application.ports.recommendation_executor import RecommendationExecutor
from adcopilot.application.ports.recommendation_repository import RecommendationRepository
from adcopilot.application.ports.repositories import (
    GoogleAdsAccountRepository,
    OAuthCredentialsRepository,
)
from adcopilot.domain.audit_log import AuditLog
from adcopilot.domain.recommendation import (
    RecommendationId,
    RecommendationKind,
    RecommendationStatus,
)

logger = structlog.get_logger(__name__)

_EXECUTORS: dict[RecommendationKind, RecommendationExecutor] | None = None


def _default_executors() -> dict[RecommendationKind, RecommendationExecutor]:
    from adcopilot.application.executors.add_negative_keyword import AddNegativeKeywordExecutor
    from adcopilot.application.executors.increase_budget import IncreaseBudgetExecutor
    from adcopilot.application.executors.pause_ad import PauseAdExecutor
    from adcopilot.application.executors.pause_keyword import PauseKeywordExecutor

    execs: list[RecommendationExecutor] = [
        PauseKeywordExecutor(),
        PauseAdExecutor(),
        AddNegativeKeywordExecutor(),
        IncreaseBudgetExecutor(),
    ]
    return {e.kind: e for e in execs}


class ExecuteRecommendationUseCase:
    def __init__(
        self,
        rec_repo: RecommendationRepository,
        audit_log_repo: AuditLogRepository,
        account_repo: GoogleAdsAccountRepository,
        credentials_repo: OAuthCredentialsRepository,
        mutations: GoogleAdsMutationsPort,
        executors: dict[RecommendationKind, RecommendationExecutor] | None = None,
    ) -> None:
        self._rec_repo = rec_repo
        self._audit_log_repo = audit_log_repo
        self._account_repo = account_repo
        self._credentials_repo = credentials_repo
        self._mutations = mutations
        self._executors = executors if executors is not None else _default_executors()

    async def execute(self, rec_id: RecommendationId) -> dict[str, Any]:
        rec = await self._rec_repo.get(rec_id)
        if rec is None:
            raise ValueError(f"Recommendation {rec_id} not found")
        if rec.status != RecommendationStatus.APPROVED:
            raise ValueError(
                f"Recommendation {rec_id} is not APPROVED (status={rec.status.value})"
            )

        executor = self._executors.get(rec.kind)
        if executor is None:
            raise ValueError(f"No executor registered for {rec.kind.value}")

        account = await self._account_repo.get(rec.account_id)
        if account is None:
            raise ValueError(f"Account {rec.account_id} not found")

        credentials = await self._credentials_repo.get(rec.account_id)
        if credentials is None:
            raise ValueError(f"No OAuth credentials for account {rec.account_id}")

        result = await executor.execute(
            rec=rec,
            mutations=self._mutations,
            refresh_token=credentials.refresh_token,
            customer_id=account.customer_id,
        )

        await self._rec_repo.update_status(rec_id, RecommendationStatus.EXECUTED)

        log = AuditLog.create_execute(
            recommendation_id=rec_id,
            account_id=rec.account_id,
            kind=rec.kind.value,
            payload=result,
            created_at=datetime.now(UTC),
        )
        await self._audit_log_repo.save(log)

        logger.info(
            "recommendation executed",
            rec_id=rec_id,
            kind=rec.kind.value,
            account_id=rec.account_id,
        )
        return result
