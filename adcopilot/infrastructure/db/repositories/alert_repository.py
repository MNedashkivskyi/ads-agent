"""SQLAlchemy implementation of AlertRepository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.alert import Alert, AlertId, AlertKind, AlertSeverity, AlertStatus
from adcopilot.domain.entities import AccountId
from adcopilot.infrastructure.db.models import AlertModel


def _model_to_domain(m: AlertModel) -> Alert:
    return Alert(
        id=AlertId(str(m.id)),
        account_id=AccountId(str(m.account_id)),
        kind=AlertKind(m.kind),
        severity=AlertSeverity(m.severity),
        status=AlertStatus(m.status),
        payload=dict(m.payload),
        message=m.message,
        created_at=m.created_at,
    )


class SqlAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, alert: Alert) -> None:
        m = AlertModel()
        m.id = uuid.UUID(alert.id)
        m.account_id = uuid.UUID(alert.account_id)
        m.kind = alert.kind.value
        m.severity = alert.severity.value
        m.status = alert.status.value
        m.payload = alert.payload
        m.message = alert.message
        m.created_at = alert.created_at
        self._session.add(m)

    async def count_since(self, account_id: AccountId, since: datetime) -> int:
        """Return number of OPEN or RESOLVED alerts created after *since*."""
        result = await self._session.execute(
            select(func.count(AlertModel.id)).where(
                AlertModel.account_id == uuid.UUID(account_id),
                AlertModel.created_at >= since,
                AlertModel.status != AlertStatus.SUPPRESSED.value,
            )
        )
        return result.scalar_one() or 0

    async def get_open(self, account_id: AccountId, kind: AlertKind) -> Alert | None:
        """Return the most recent OPEN alert of this kind for the account."""
        result = await self._session.execute(
            select(AlertModel)
            .where(
                AlertModel.account_id == uuid.UUID(account_id),
                AlertModel.kind == kind.value,
                AlertModel.status == AlertStatus.OPEN.value,
            )
            .order_by(AlertModel.created_at.desc())
            .limit(1)
        )
        m = result.scalar_one_or_none()
        return _model_to_domain(m) if m else None
