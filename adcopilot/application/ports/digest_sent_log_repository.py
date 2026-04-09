"""DigestSentLogRepository port (Protocol)."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from adcopilot.domain.entities import UserId


class DigestSentLogRepository(Protocol):
    async def was_sent_today(self, user_id: UserId, today: date) -> bool: ...

    async def record(self, user_id: UserId, sent_date: date, rec_ids: list[str]) -> None: ...
