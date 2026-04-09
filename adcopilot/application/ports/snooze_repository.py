"""SnoozeRepository port (Protocol)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import Recommendation


class SnoozeRepository(Protocol):
    async def save_snooze(self, rec: Recommendation, snoozed_until: datetime) -> None: ...

    async def get_active_snooze_keys(
        self, account_id: AccountId, now: datetime
    ) -> set[tuple[str, str]]:
        """Return set of (kind_value, target_hash) for active snoozes on the account."""
        ...
