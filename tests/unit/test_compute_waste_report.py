"""Unit test for ComputeAndStoreWasteReportUseCase (Audit Funnel T1.5)."""

from __future__ import annotations

from datetime import date

from adcopilot.application.audit.waste_engine import AuditDataset, SearchTermRow
from adcopilot.application.use_cases.compute_waste_report import (
    ComputeAndStoreWasteReportUseCase,
)
from adcopilot.domain.audit import ReportConfidence, WasteReport

_M = 1_000_000


class _FakeReportRepo:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None

    async def create(self, **kw: object) -> WasteReport:
        self.created = kw
        return WasteReport(
            id="rep-1",
            window_start=kw["window_start"],  # type: ignore[arg-type]
            window_end=kw["window_end"],  # type: ignore[arg-type]
            total_spend_micros=kw["total_spend_micros"],  # type: ignore[arg-type]
            headline_waste_micros=kw["headline_waste_micros"],  # type: ignore[arg-type]
            measurement_gap_pct=kw["measurement_gap_pct"],  # type: ignore[arg-type]
            confidence=kw["confidence"],  # type: ignore[arg-type]
            audit_session_id=kw.get("audit_session_id"),  # type: ignore[arg-type]
            account_id=kw.get("account_id"),  # type: ignore[arg-type]
            methodology_version=kw.get("methodology_version", "1"),  # type: ignore[arg-type]
        )


class _FakeFindingRepo:
    def __init__(self) -> None:
        self.added: list[dict[str, object]] = []

    async def add(self, **kw: object) -> None:
        self.added.append(kw)


async def test_compute_and_store_persists_report_and_findings() -> None:
    reports = _FakeReportRepo()
    findings = _FakeFindingRepo()
    dataset = AuditDataset(
        window_start=date(2026, 5, 1),
        window_end=date(2026, 5, 31),
        total_spend_micros=10_000 * _M,
        vertical="e-commerce",
        city="Warszawa",
        search_terms=[
            SearchTermRow("kurs za darmo", clicks=20, conversions=0, cost_micros=200 * _M)
        ],
        measurement_gap_pct=0.5,
    )

    report = await ComputeAndStoreWasteReportUseCase(reports, findings).execute(
        dataset, audit_session_id="sess-1"
    )

    assert report.id == "rep-1"
    assert reports.created is not None
    assert reports.created["headline_waste_micros"] == 200 * _M
    assert reports.created["confidence"] is ReportConfidence.MEDIUM
    assert reports.created["audit_session_id"] == "sess-1"
    assert reports.created["methodology_version"] == "1"

    categories = {f["category"].value for f in findings.added}  # type: ignore[attr-defined]
    assert "negative_blockable" in categories  # confirmed waste from the junk-intent term
    assert "measurement_gap" in categories  # qualitative, no amount
