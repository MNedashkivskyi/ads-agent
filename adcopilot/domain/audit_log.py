"""AuditLog domain model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, NewType

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationId

AuditLogId = NewType("AuditLogId", str)


def _new_audit_log_id() -> AuditLogId:
    return AuditLogId(str(uuid.uuid4()))


@dataclass(frozen=True)
class AuditLog:
    id: AuditLogId
    recommendation_id: RecommendationId
    account_id: AccountId
    kind: str  # RecommendationKind.value
    action: str  # "EXECUTE" | "UNDO"
    payload: dict[str, Any]
    created_at: datetime

    @classmethod
    def create_execute(
        cls,
        recommendation_id: RecommendationId,
        account_id: AccountId,
        kind: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> AuditLog:
        return cls(
            id=_new_audit_log_id(),
            recommendation_id=recommendation_id,
            account_id=account_id,
            kind=kind,
            action="EXECUTE",
            payload=payload,
            created_at=created_at,
        )
