"""Port: Alert repository."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from adcopilot.domain.alert import Alert, AlertKind
from adcopilot.domain.entities import AccountId


class AlertRepository(Protocol):
    async def save(self, alert: Alert) -> None: ...

    async def count_since(self, account_id: AccountId, since: datetime) -> int:
        """Return number of OPEN/RESOLVED alerts created after *since*."""
        ...

    async def get_open(self, account_id: AccountId, kind: AlertKind) -> Alert | None:
        """Return the most recent OPEN alert of this kind for the account."""
        ...
