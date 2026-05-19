"""NotificationRepository port (Protocol)."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.notification import Notification


class NotificationRepository(Protocol):
    async def save(self, notification: Notification) -> None: ...

    async def list_for_user(
        self, user_id: str, limit: int = 50, offset: int = 0
    ) -> list[Notification]: ...

    async def get(self, notification_id: str) -> Notification | None: ...

    async def mark_read(self, notification_id: str) -> None: ...

    async def mark_all_read(self, user_id: str) -> None: ...

    async def count_unread(self, user_id: str) -> int: ...
