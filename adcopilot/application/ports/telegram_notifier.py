"""TelegramNotifier port (Protocol)."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.recommendation import Recommendation


class TelegramNotifier(Protocol):
    async def send_digest(self, chat_id: int, recommendations: list[Recommendation]) -> None: ...

    async def send_execution_failed(
        self, chat_id: int, recommendation: Recommendation, error_message: str
    ) -> None: ...

    async def send_reauth_required(
        self, chat_id: int, account_name: str, reauth_url: str | None = None
    ) -> None: ...
