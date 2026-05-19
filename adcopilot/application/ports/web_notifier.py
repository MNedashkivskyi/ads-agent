"""WebNotifier port (Protocol)."""

from __future__ import annotations

from typing import Protocol


class WebNotifier(Protocol):
    async def send_digest(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None: ...

    async def send_alert(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None: ...

    async def send_execution_result(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None: ...

    async def send_reauth_required(
        self, user_id: str, title: str, body: str, metadata: dict | None = None
    ) -> None: ...
