"""SQLAlchemy implementation of AlertRepository."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.alert import Alert, AlertId, AlertKind, AlertSeverity, AlertStatus
from adcopilot.domain.entities import AccountId
from adcopilot.infrastructure.db.models import AlertKindSuppressionModel, AlertModel


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
        acknowledged_at=m.acknowledged_at,
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

    async def acknowledge(self, alert_id: AlertId, acknowledged_at: datetime) -> None:
        """Mark an alert as RESOLVED and record the acknowledgement timestamp."""
        await self._session.execute(
            update(AlertModel)
            .where(AlertModel.id == uuid.UUID(alert_id))
            .values(status=AlertStatus.RESOLVED.value, acknowledged_at=acknowledged_at)
        )

    async def suppress_kind(
        self, account_id: AccountId, kind: AlertKind, suppressed_until: datetime
    ) -> None:
        """Upsert a kind-level suppression window for the account."""
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        stmt = (
            pg_insert(AlertKindSuppressionModel)
            .values(
                id=uuid.uuid4(),
                account_id=uuid.UUID(account_id),
                kind=kind.value,
                suppressed_until=suppressed_until,
            )
            .on_conflict_do_update(
                constraint="uq_alert_kind_suppressions_acct_kind",
                set_={"suppressed_until": suppressed_until},
            )
        )
        await self._session.execute(stmt)

    async def is_kind_suppressed(
        self, account_id: AccountId, kind: AlertKind, now: datetime
    ) -> bool:
        """Return True if the given kind is currently suppressed for the account."""
        result = await self._session.execute(
            select(AlertKindSuppressionModel).where(
                AlertKindSuppressionModel.account_id == uuid.UUID(account_id),
                AlertKindSuppressionModel.kind == kind.value,
                AlertKindSuppressionModel.suppressed_until > now,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_for_account(self, account_id: AccountId, limit: int = 50) -> list[Alert]:
        """Return alerts for the account, newest first."""
        result = await self._session.execute(
            select(AlertModel)
            .where(AlertModel.account_id == uuid.UUID(account_id))
            .order_by(AlertModel.created_at.desc())
            .limit(limit)
        )
        return [_model_to_domain(m) for m in result.scalars().all()]
