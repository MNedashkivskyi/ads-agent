"""AutoApplyUseCase — select and auto-approve low-risk recommendations (T3.1).

Given an account that has opted into auto-apply, this selects the eligible
low-risk pending recommendations (see ``adcopilot.domain.auto_apply``), marks
them APPROVED, and writes an audit-log entry with ``actor=auto`` for each. It
returns the approved recommendation ids so the caller can enqueue execution.

It does NOT execute anything itself: execution stays in
``execute_recommendation_task``, where SpendGuard's preventive check is enforced
before any Google Ads mutation. The per-day cap is applied per detection run
(once a recommendation is approved it leaves the pending set, so it is not
re-approved on later runs).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from adcopilot.domain.audit_log import AuditLog, _new_audit_log_id
from adcopilot.domain.auto_apply import AutoApplySettings, select_for_auto_apply
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationId, RecommendationStatus

logger = structlog.get_logger(__name__)


class AutoApplyUseCase:
    def __init__(
        self,
        rec_repo: Any,
        settings_repo: Any,
        audit_repo: Any,
    ) -> None:
        self._rec_repo = rec_repo
        self._settings_repo = settings_repo
        self._audit_repo = audit_repo

    async def select_and_approve(self, account_id: AccountId) -> list[RecommendationId]:
        """Approve eligible low-risk recs for an opted-in account.

        Returns the approved recommendation ids (empty if auto-apply is off for
        the account or nothing is eligible).
        """
        settings: AutoApplySettings | None = await self._settings_repo.get(str(account_id))
        if settings is None or not settings.enabled:
            return []

        pending = await self._rec_repo.list_pending(account_id)
        selected = select_for_auto_apply(pending, settings)
        approved: list[RecommendationId] = []
        for rec in selected:
            await self._rec_repo.update_status(rec.id, RecommendationStatus.APPROVED)
            await self._audit_repo.save(
                AuditLog(
                    id=_new_audit_log_id(),
                    recommendation_id=rec.id,
                    account_id=account_id,
                    kind=rec.kind.value,
                    action="AUTO_APPROVE",
                    payload={
                        "actor": "auto",
                        "severity": rec.severity.value,
                        "max_risk": settings.max_risk.value,
                    },
                    created_at=datetime.now(UTC),
                )
            )
            approved.append(rec.id)

        if approved:
            logger.info(
                "auto_apply.approved",
                account_id=str(account_id),
                count=len(approved),
                cap=settings.max_changes_per_day,
            )
        return approved
