"""SqlNotificationRepository — SQLAlchemy async implementation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.notification import Notification, NotificationId, NotificationType
from adcopilot.infrastructure.db.models import NotificationModel


def _to_domain(m: NotificationModel) -> Notification:
    return Notification(
        id=NotificationId(str(m.id)),
        user_id=m.user_id,
        notification_type=NotificationType(m.notification_type),
        title=m.title,
        body=m.body,
        metadata=m.metadata_ or {},
        read_at=m.read_at,
        created_at=m.created_at,
    )


class SqlNotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, notification: Notification) -> None:
        m = NotificationModel()
        m.id = uuid.UUID(notification.id)
        m.user_id = notification.user_id
        m.notification_type = notification.notification_type.value
        m.title = notification.title
        m.body = notification.body
        m.metadata_ = notification.metadata
        m.read_at = notification.read_at
        m.created_at = notification.created_at
        self._session.add(m)

    async def list_for_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[Notification]:
        result = await self._session.execute(
            select(NotificationModel)
            .where(NotificationModel.user_id == user_id)
            .order_by(NotificationModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return [_to_domain(m) for m in result.scalars().all()]

    async def get(self, notification_id: str) -> Notification | None:
        result = await self._session.execute(
            select(NotificationModel).where(
                NotificationModel.id == uuid.UUID(notification_id)
            )
        )
        m = result.scalar_one_or_none()
        return _to_domain(m) if m else None

    async def mark_read(self, notification_id: str) -> None:
        await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.id == uuid.UUID(notification_id),
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )

    async def mark_all_read(self, user_id: str) -> None:
        await self._session.execute(
            update(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
            .values(read_at=datetime.now(UTC))
        )

    async def count_unread(self, user_id: str) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(NotificationModel)
            .where(
                NotificationModel.user_id == user_id,
                NotificationModel.read_at.is_(None),
            )
        )
        return result.scalar_one()
