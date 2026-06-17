"""Unit tests for BridgeAuditSessionUseCase (Audit Funnel — onboarding bridge)."""

from __future__ import annotations

from types import SimpleNamespace

from adcopilot.application.use_cases.bridge_audit_session import BridgeAuditSessionUseCase
from adcopilot.domain.audit import AuditSession


class _FakeSessions:
    def __init__(self, session: AuditSession | None) -> None:
        self._session = session
        self.promoted: tuple[str, str, str] | None = None

    async def get(self, session_id: str) -> AuditSession | None:
        return self._session

    async def promote(self, session_id: str, *, user_id: str, account_id: str) -> bool:
        self.promoted = (session_id, user_id, account_id)
        return True


class _FakeAccounts:
    def __init__(self, account: object | None) -> None:
        self._account = account

    async def get_by_customer_id(self, customer_id: str):  # noqa: ANN201
        return self._account


class _FakeReports:
    def __init__(self) -> None:
        self.linked: tuple[str, str] | None = None

    async def set_account_for_session(self, audit_session_id: str, account_id: str) -> None:
        self.linked = (audit_session_id, account_id)


def _session(**kw) -> AuditSession:  # noqa: ANN003
    return AuditSession(id="s1", google_customer_id="1234567890", **kw)


async def test_bridges_when_customer_matches_owned_account() -> None:
    sessions = _FakeSessions(_session())
    accounts = _FakeAccounts(SimpleNamespace(id="acc-1", user_id="u1", customer_id="1234567890"))
    reports = _FakeReports()

    account_id = await BridgeAuditSessionUseCase(sessions, accounts, reports).execute(
        session_id="s1", user_id="u1"
    )

    assert account_id == "acc-1"
    assert sessions.promoted == ("s1", "u1", "acc-1")
    assert reports.linked == ("s1", "acc-1")


async def test_no_bridge_when_account_owned_by_other_user() -> None:
    sessions = _FakeSessions(_session())
    accounts = _FakeAccounts(
        SimpleNamespace(id="acc-1", user_id="someone-else", customer_id="1234567890")
    )
    result = await BridgeAuditSessionUseCase(sessions, accounts, _FakeReports()).execute(
        session_id="s1", user_id="u1"
    )
    assert result is None
    assert sessions.promoted is None


async def test_no_bridge_when_no_matching_account() -> None:
    sessions = _FakeSessions(_session())
    result = await BridgeAuditSessionUseCase(sessions, _FakeAccounts(None), _FakeReports()).execute(
        session_id="s1", user_id="u1"
    )
    assert result is None


async def test_no_bridge_when_already_promoted_or_no_customer() -> None:
    promoted_session = _session(user_id="u0")  # is_promoted == True
    r1 = await BridgeAuditSessionUseCase(
        _FakeSessions(promoted_session), _FakeAccounts(None), _FakeReports()
    ).execute(session_id="s1", user_id="u1")
    assert r1 is None

    no_customer = AuditSession(id="s1", google_customer_id=None)
    r2 = await BridgeAuditSessionUseCase(
        _FakeSessions(no_customer), _FakeAccounts(None), _FakeReports()
    ).execute(session_id="s1", user_id="u1")
    assert r2 is None
