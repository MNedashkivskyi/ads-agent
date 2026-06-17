"""Orchestrate a free audit scan (Audit Funnel Phase 2 / T2.1).

Discovers the connected customer, pulls read-only data, builds the dataset, runs
the waste engine + persists the report, and walks the session through
PENDING -> SCANNING -> READY (or FAILED). The Google Ads reader is injected, so
this is fully unit-testable against a fake; the live GAQL adapter and the Celery
wrapper are thin.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol

from adcopilot.application.audit.dataset_builder import build_audit_dataset
from adcopilot.application.audit.scan_reader import AuditScanReader
from adcopilot.application.audit.waste_engine import AuditDataset
from adcopilot.domain.audit import AuditStatus, WasteReport


class _SessionRepo(Protocol):
    async def set_status(self, session_id: str, status: AuditStatus) -> None: ...

    async def set_customer_id(self, session_id: str, google_customer_id: str) -> None: ...


class _ReportComputer(Protocol):
    async def execute(
        self,
        dataset: AuditDataset,
        *,
        audit_session_id: str | None = ...,
        account_id: str | None = ...,
    ) -> WasteReport: ...


def _customer_id_from_resource(resource_name: str) -> str:
    """``customers/1234567890`` -> ``1234567890`` (passes plain ids through)."""
    return resource_name.rsplit("/", 1)[-1]


class RunAuditScanUseCase:
    def __init__(
        self, reader: AuditScanReader, sessions: _SessionRepo, compute: _ReportComputer
    ) -> None:
        self._reader = reader
        self._sessions = sessions
        self._compute = compute

    async def execute(
        self,
        *,
        audit_session_id: str,
        refresh_token: str,
        today: date,
        days: int = 30,
    ) -> str | None:
        """Run the scan. Returns the report id, or None when there is nothing to scan.

        Exceptions propagate: the Celery task marks the session FAILED in its own
        transaction, because a rolled-back transaction here could not persist it.
        """
        customers = await self._reader.accessible_customers(refresh_token)
        if not customers:
            await self._sessions.set_status(audit_session_id, AuditStatus.FAILED)
            return None

        customer_id = _customer_id_from_resource(customers[0])
        await self._sessions.set_customer_id(audit_session_id, customer_id)
        await self._sessions.set_status(audit_session_id, AuditStatus.SCANNING)

        raw = await self._reader.pull(refresh_token, customer_id, days)
        dataset = build_audit_dataset(
            raw,
            window_start=today - timedelta(days=days),
            window_end=today,
            days=days,
        )
        report = await self._compute.execute(dataset, audit_session_id=audit_session_id)

        await self._sessions.set_status(audit_session_id, AuditStatus.READY)
        return report.id
