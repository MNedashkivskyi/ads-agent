"""Compute a waste report and persist it with its findings (Audit Funnel T1.5).

Runs the pure ``waste_engine`` over a dataset, then writes the resulting
``WasteReport`` and one ``WasteFinding`` per finding. The scan worker (Phase 2)
assembles the dataset and calls this; here we just compute and store.
"""

from __future__ import annotations

from typing import Protocol

from adcopilot.application.audit.methodology import METHODOLOGY_VERSION
from adcopilot.application.audit.waste_engine import (
    DEFAULT_CONFIG,
    AuditDataset,
    WasteConfig,
    compute_waste,
)
from adcopilot.domain.audit import (
    FindingTier,
    ReportConfidence,
    WasteCategory,
    WasteFinding,
    WasteReport,
)


class _ReportRepo(Protocol):
    async def create(
        self,
        *,
        window_start: object,
        window_end: object,
        total_spend_micros: int,
        headline_waste_micros: int,
        measurement_gap_pct: float,
        confidence: ReportConfidence,
        audit_session_id: str | None = ...,
        account_id: str | None = ...,
        methodology_version: str = ...,
    ) -> WasteReport: ...


class _FindingRepo(Protocol):
    async def add(
        self,
        *,
        report_id: str,
        category: WasteCategory,
        tier: FindingTier,
        title: str,
        severity: str = ...,
        amount_micros: int | None = ...,
        evidence: dict[str, object] | None = ...,
    ) -> WasteFinding: ...


class ComputeAndStoreWasteReportUseCase:
    def __init__(self, reports: _ReportRepo, findings: _FindingRepo) -> None:
        self._reports = reports
        self._findings = findings

    async def execute(
        self,
        dataset: AuditDataset,
        *,
        audit_session_id: str | None = None,
        account_id: str | None = None,
        config: WasteConfig = DEFAULT_CONFIG,
    ) -> WasteReport:
        comp = compute_waste(dataset, config)
        report = await self._reports.create(
            window_start=comp.window_start,
            window_end=comp.window_end,
            total_spend_micros=comp.total_spend_micros,
            headline_waste_micros=comp.headline_waste_micros,
            measurement_gap_pct=comp.measurement_gap_pct,
            confidence=comp.confidence,
            audit_session_id=audit_session_id,
            account_id=account_id,
            methodology_version=METHODOLOGY_VERSION,
        )
        for f in comp.findings:
            await self._findings.add(
                report_id=report.id,
                category=f.category,
                tier=f.tier,
                title=f.title,
                severity=f.severity,
                amount_micros=f.amount_micros,
                evidence=f.evidence,
            )
        return report
