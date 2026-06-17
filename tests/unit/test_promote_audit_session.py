"""Unit test for PromoteAuditSessionUseCase (Audit Funnel T0.3)."""

from __future__ import annotations

from adcopilot.application.use_cases.promote_audit_session import PromoteAuditSessionUseCase


class _FakeSessionRepo:
    def __init__(self, *, already_promoted: bool = False) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self._already = already_promoted

    async def promote(self, session_id: str, *, user_id: str, account_id: str) -> bool:
        self.calls.append((session_id, user_id, account_id))
        return not self._already


async def test_promote_calls_repo_and_returns_true() -> None:
    repo = _FakeSessionRepo()
    result = await PromoteAuditSessionUseCase(repo).execute(
        session_id="s1", user_id="u1", account_id="a1"
    )
    assert result is True
    assert repo.calls == [("s1", "u1", "a1")]


async def test_promote_is_idempotent_returns_false_when_already_promoted() -> None:
    repo = _FakeSessionRepo(already_promoted=True)
    result = await PromoteAuditSessionUseCase(repo).execute(
        session_id="s1", user_id="u1", account_id="a1"
    )
    assert result is False
