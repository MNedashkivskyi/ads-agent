"""Unit tests for RecoveryPortfolioUseCase (Phase 5 — agency portfolio, pure)."""

from __future__ import annotations

from types import SimpleNamespace

from adcopilot.application.use_cases.recovery_portfolio import RecoveryPortfolioUseCase

_M = 1_000_000


class _FakeAccounts:
    def __init__(self, accounts: list[object]) -> None:
        self._accounts = accounts

    async def list_for_user(self, user_id: object) -> list[object]:
        return self._accounts


class _FakeLedger:
    def __init__(self, recovered: dict[str, int], counts: dict[str, int]) -> None:
        self._recovered = recovered
        self._counts = counts

    async def recovered_total_micros(self, account_id: str) -> int:
        return self._recovered.get(account_id, 0)

    async def list_for_account(self, account_id: str) -> list[object]:
        return [object()] * self._counts.get(account_id, 0)


class _FakeReports:
    def __init__(self, reports: dict[str, object]) -> None:
        self._reports = reports

    async def get_for_account(self, account_id: str) -> object | None:
        return self._reports.get(account_id)


def _account(account_id: str, customer_id: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=account_id,
        customer_id=customer_id,
        descriptive_name=f"Acct {customer_id}",
        currency="PLN",
    )


async def test_portfolio_aggregates_across_accounts() -> None:
    accounts = [_account("a1", "111"), _account("a2", "222")]
    ledger = _FakeLedger(recovered={"a1": 300 * _M, "a2": 100 * _M}, counts={"a1": 2, "a2": 1})
    reports = _FakeReports({"a1": SimpleNamespace(annual_waste_micros=1_200 * _M)})  # a2: no audit

    result = await RecoveryPortfolioUseCase(_FakeAccounts(accounts), ledger, reports).execute(
        user_id="u1"
    )

    assert result["account_count"] == 2
    assert result["totals"] == {
        "recovered_micros": 400 * _M,
        "identified_annual_waste_micros": 1_200 * _M,
        "applied_count": 3,
    }
    assert result["accounts"][0]["has_audit"] is True
    assert result["accounts"][1]["has_audit"] is False
    assert result["accounts"][0]["recovered_micros"] == 300 * _M


async def test_portfolio_empty_when_no_accounts() -> None:
    result = await RecoveryPortfolioUseCase(
        _FakeAccounts([]), _FakeLedger({}, {}), _FakeReports({})
    ).execute(user_id="u1")

    assert result["account_count"] == 0
    assert result["currency"] == "PLN"
    assert result["totals"]["recovered_micros"] == 0
    assert result["accounts"] == []
