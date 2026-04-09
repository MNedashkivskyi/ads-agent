"""AuditLogRepository port (Protocol)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from adcopilot.domain.audit_log import AuditLog
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationId


class AuditLogRepository(Protocol):
    async def save(self, log: AuditLog) -> None: ...

    async def get_latest_execute(self, rec_id: RecommendationId) -> AuditLog | None:
        """Return the most recent EXECUTE audit entry for this recommendation."""
        ...

    async def list_recent_executes(
        self, account_ids: list[AccountId], since: datetime
    ) -> list[AuditLog]:
        """Return EXECUTE audit entries for the given accounts since a point in time,
        newest first."""
        ...
