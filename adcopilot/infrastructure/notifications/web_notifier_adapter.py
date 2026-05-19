"""SqlWebNotifier — persists notifications to the DB."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.notification import NotificationType
from adcopilot.infrastructure.db.models import NotificationModel


class SqlWebNotifier:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _send(
        self,
        user_id: str,
        notification_type: NotificationType,
        title: str,
        body: str,
        metadata: dict | None,
    ) -> None:
        m = NotificationModel()
        m.id = uuid.uuid4()
        m.user_id = user_id
        m.notification_type = notification_type.value
        m.title = title
        m.body = body
        m.metadata_ = metadata or {}
        self._session.add(m)

    async def send_digest(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None:
        await self._send(user_id, NotificationType.DIGEST, title, body, metadata)

    async def send_alert(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None:
        await self._send(user_id, NotificationType.ALERT, title, body, metadata)

    async def send_execution_result(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None:
        await self._send(user_id, NotificationType.EXECUTION_RESULT, title, body, metadata)

    async def send_reauth_required(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None:
        await self._send(user_id, NotificationType.REAUTH_REQUIRED, title, body, metadata)

    async def send_insight(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None:
        await self._send(user_id, NotificationType.INSIGHT, title, body, metadata)
