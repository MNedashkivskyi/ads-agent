"""Fake TelegramNotifier for unit tests."""

from __future__ import annotations

from adcopilot.domain.recommendation import Recommendation


class FakeTelegramNotifier:
    """Records send_digest calls without hitting the network."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_digest(self, chat_id: int, recommendations: list[Recommendation]) -> None:
        self.calls.append({"chat_id": chat_id, "recommendations": list(recommendations)})
