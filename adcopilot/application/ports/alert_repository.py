"""Port: Alert repository."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from adcopilot.domain.alert import Alert, AlertId, AlertKind
from adcopilot.domain.entities import AccountId


class AlertRepository(Protocol):
    async def save(self, alert: Alert) -> None: ...

    async def count_since(self, account_id: AccountId, since: datetime) -> int:
        """Return number of OPEN/RESOLVED alerts created after *since*."""
        ...

    async def get_open(self, account_id: AccountId, kind: AlertKind) -> Alert | None:
        """Return the most recent OPEN alert of this kind for the account."""
        ...

    async def acknowledge(self, alert_id: AlertId, acknowledged_at: datetime) -> None:
        """Mark an alert as RESOLVED and set acknowledged_at."""
        ...

    async def suppress_kind(
        self, account_id: AccountId, kind: AlertKind, suppressed_until: datetime
    ) -> None:
        """Upsert a kind-level suppression window for the account."""
        ...

    async def is_kind_suppressed(
        self, account_id: AccountId, kind: AlertKind, now: datetime
    ) -> bool:
        """Return True if the given kind is currently suppressed for the account."""
        ...

    async def list_for_account(self, account_id: AccountId, limit: int = 50) -> list[Alert]:
        """Return alerts for the account, newest first."""
        ...
