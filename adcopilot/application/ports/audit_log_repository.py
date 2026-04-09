"""AuditLogRepository port (Protocol)."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.audit_log import AuditLog


class AuditLogRepository(Protocol):
    async def save(self, log: AuditLog) -> None: ...
