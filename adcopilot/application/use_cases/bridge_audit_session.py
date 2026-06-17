"""Bridge an anonymous audit to a freshly-linked account (Audit Funnel — onboarding bridge).

When a visitor signs up from their audit and links the *same* Google Ads account
(write-enabled), this claims the audit: it promotes the anonymous session to the
user + account and ties the WasteReport to the account, so the product can show
the audit headline and the first detection run corroborates it.

Matching is by ``google_customer_id`` (approved decision: auto-promote on match).
The caller kicks off the first snapshot for the returned account id.
"""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.audit import AuditSession


class _Account(Protocol):
    id: object
    user_id: object
    customer_id: str


class _SessionRepo(Protocol):
    async def get(self, session_id: str) -> AuditSession | None: ...
    async def promote(self, session_id: str, *, user_id: str, account_id: str) -> bool: ...


class _AccountRepo(Protocol):
    async def get_by_customer_id(self, customer_id: str) -> _Account | None: ...


class _ReportRepo(Protocol):
    async def set_account_for_session(self, audit_session_id: str, account_id: str) -> None: ...


class BridgeAuditSessionUseCase:
    def __init__(
        self, sessions: _SessionRepo, accounts: _AccountRepo, reports: _ReportRepo
    ) -> None:
        self._sessions = sessions
        self._accounts = accounts
        self._reports = reports

    async def execute(self, *, session_id: str, user_id: str) -> str | None:
        """Bridge the session to the user's matching linked account.

        Returns the account id when bridged (caller kicks off the first snapshot),
        or None when there is nothing to bridge: unknown session, customer id not
        yet resolved, already promoted, or no matching account owned by the user.
        """
        session = await self._sessions.get(session_id)
        if session is None or not session.google_customer_id or session.is_promoted:
            return None

        account = await self._accounts.get_by_customer_id(session.google_customer_id)
        if account is None or str(account.user_id) != user_id:
            return None

        promoted = await self._sessions.promote(
            session_id, user_id=user_id, account_id=str(account.id)
        )
        if not promoted:
            return None

        await self._reports.set_account_for_session(session_id, str(account.id))
        return str(account.id)
