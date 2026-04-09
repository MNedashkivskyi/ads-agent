"""TelegramNotifier port (Protocol)."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.recommendation import Recommendation


class TelegramNotifier(Protocol):
    async def send_digest(self, chat_id: int, recommendations: list[Recommendation]) -> None: ...
