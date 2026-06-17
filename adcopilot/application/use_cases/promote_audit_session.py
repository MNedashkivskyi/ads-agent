"""Promote an anonymous audit session to a real user/account (Audit Funnel T0.3).

When a visitor signs up from their waste report, the previously anonymous
``AuditSession`` is claimed by the new user and linked to their connected
account. The report and its findings already reference the session, so they are
preserved automatically. Promotion is idempotent: a session already attached to
a user is not re-promoted.
"""

from __future__ import annotations

from typing import Protocol


class _SessionRepo(Protocol):
    async def promote(self, session_id: str, *, user_id: str, account_id: str) -> bool: ...


class PromoteAuditSessionUseCase:
    def __init__(self, sessions: _SessionRepo) -> None:
        self._sessions = sessions

    async def execute(self, *, session_id: str, user_id: str, account_id: str) -> bool:
        """Attach ``user_id``/``account_id`` to the session.

        Returns True when this call performed the promotion, False when the
        session was already promoted or does not exist.
        """
        return await self._sessions.promote(session_id, user_id=user_id, account_id=account_id)
