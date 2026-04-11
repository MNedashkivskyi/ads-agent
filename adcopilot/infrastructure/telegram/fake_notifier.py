"""Fake TelegramNotifier for unit tests."""

from __future__ import annotations

from adcopilot.domain.recommendation import Recommendation


class FakeTelegramNotifier:
    """Records send_digest calls without hitting the network."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def send_digest(self, chat_id: int, recommendations: list[Recommendation]) -> None:
        self.calls.append({"chat_id": chat_id, "recommendations": list(recommendations)})

    async def send_execution_failed(
        self, chat_id: int, recommendation: Recommendation, error_message: str
    ) -> None:
        self.calls.append(
            {
                "method": "send_execution_failed",
                "chat_id": chat_id,
                "recommendation": recommendation,
                "error_message": error_message,
            }
        )

    async def send_reauth_required(
        self, chat_id: int, account_name: str, reauth_url: str | None = None
    ) -> None:
        self.calls.append(
            {
                "method": "send_reauth_required",
                "chat_id": chat_id,
                "account_name": account_name,
                "reauth_url": reauth_url,
            }
        )
