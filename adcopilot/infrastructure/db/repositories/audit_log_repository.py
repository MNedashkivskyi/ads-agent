"""SQLAlchemy implementation of AuditLogRepository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.audit_log import AuditLog, AuditLogId
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import RecommendationId
from adcopilot.infrastructure.db.models import AuditLogModel


def _model_to_domain(m: AuditLogModel) -> AuditLog:
    return AuditLog(
        id=AuditLogId(str(m.id)),
        recommendation_id=RecommendationId(str(m.recommendation_id)),
        account_id=AccountId(str(m.account_id)),
        kind=m.kind,
        action=m.action,
        payload=dict(m.payload),
        created_at=m.created_at,
    )


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

    async def get_latest_execute(self, rec_id: RecommendationId) -> AuditLog | None:
        result = await self._session.execute(
            select(AuditLogModel)
            .where(
                AuditLogModel.recommendation_id == uuid.UUID(rec_id),
                AuditLogModel.action == "EXECUTE",
            )
            .order_by(AuditLogModel.created_at.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        return _model_to_domain(m) if m else None

    async def list_recent_executes(
        self, account_ids: list[AccountId], since: datetime
    ) -> list[AuditLog]:
        if not account_ids:
            return []
        uuids = [uuid.UUID(aid) for aid in account_ids]
        result = await self._session.execute(
            select(AuditLogModel)
            .where(
                AuditLogModel.account_id.in_(uuids),
                AuditLogModel.action == "EXECUTE",
                AuditLogModel.created_at >= since,
            )
            .order_by(AuditLogModel.created_at.desc())
        )
        return [_model_to_domain(m) for m in result.scalars().all()]
