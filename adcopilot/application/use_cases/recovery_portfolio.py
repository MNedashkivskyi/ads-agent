"""Recovery rolled up across all of a user's accounts (Phase 5 — agency portfolio).

Aggregates the per-account recovery meter into one portfolio view: total recovered,
total audit-identified annual waste, and applied-fix count, plus a per-account row.
Pure orchestration over injected repos so it's unit-testable without a database.
"""

from __future__ import annotations

from typing import Protocol


class _Account(Protocol):
    id: object
    customer_id: str
    descriptive_name: str
    currency: str


class _AccountsRepo(Protocol):
    async def list_for_user(self, user_id: object) -> list[_Account]: ...


class _Report(Protocol):
    annual_waste_micros: int


class _LedgerRepo(Protocol):
    async def recovered_total_micros(self, account_id: str) -> int: ...
    async def list_for_account(self, account_id: str) -> list[object]: ...


class _ReportsRepo(Protocol):
    async def get_for_account(self, account_id: str) -> _Report | None: ...


class RecoveryPortfolioUseCase:
    def __init__(self, accounts: _AccountsRepo, ledger: _LedgerRepo, reports: _ReportsRepo) -> None:
        self._accounts = accounts
        self._ledger = ledger
        self._reports = reports

    async def execute(self, *, user_id: object) -> dict[str, object]:
        accounts = await self._accounts.list_for_user(user_id)
        rows: list[dict[str, object]] = []
        total_recovered = 0
        total_identified = 0
        total_applied = 0
        for acc in accounts:
            account_id = str(acc.id)
            recovered = await self._ledger.recovered_total_micros(account_id)
            applied = len(await self._ledger.list_for_account(account_id))
            report = await self._reports.get_for_account(account_id)
            identified = report.annual_waste_micros if report else 0
            rows.append(
                {
                    "account_id": account_id,
                    "customer_id": acc.customer_id,
                    "name": acc.descriptive_name,
                    "recovered_micros": recovered,
                    "applied_count": applied,
                    "identified_annual_waste_micros": identified,
                    "has_audit": report is not None,
                }
            )
            total_recovered += recovered
            total_identified += identified
            total_applied += applied
        return {
            "account_count": len(rows),
            "currency": accounts[0].currency if accounts else "PLN",
            "totals": {
                "recovered_micros": total_recovered,
                "identified_annual_waste_micros": total_identified,
                "applied_count": total_applied,
            },
            "accounts": rows,
        }
