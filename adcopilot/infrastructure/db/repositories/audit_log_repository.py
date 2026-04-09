"""SQLAlchemy implementation of AuditLogRepository."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.audit_log import AuditLog
from adcopilot.infrastructure.db.models import AuditLogModel


class SqlAuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, log: AuditLog) -> None:
        m = AuditLogModel()
        m.id = uuid.UUID(log.id)
        m.recommendation_id = uuid.UUID(log.recommendation_id)
        m.account_id = uuid.UUID(log.account_id)
        m.kind = log.kind
        m.action = log.action
        m.payload = log.payload
        m.created_at = log.created_at
        self._session.add(m)
        await self._session.flush()
