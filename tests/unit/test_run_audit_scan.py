"""Unit tests for RunAuditScanUseCase orchestration (Audit Funnel T2.1)."""

from __future__ import annotations

from datetime import date

from adcopilot.application.audit.scan_reader import AuditRawData
from adcopilot.application.use_cases.compute_waste_report import (
    ComputeAndStoreWasteReportUseCase,
)
from adcopilot.application.use_cases.run_audit_scan import RunAuditScanUseCase
from adcopilot.domain.audit import AuditStatus, WasteReport
from adcopilot.domain.snapshot import CampaignSnapshot, SearchTermSnapshot

_D = date(2026, 5, 31)
_M = 1_000_000


class _FakeReader:
    def __init__(self, customers: list[str], raw: AuditRawData) -> None:
        self._customers = customers
        self._raw = raw
        self.pulled: tuple[str, int] | None = None

    async def accessible_customers(self, refresh_token: str) -> list[str]:
        return self._customers

    async def pull(self, refresh_token: str, customer_id: str, days: int) -> AuditRawData:
        self.pulled = (customer_id, days)
        return self._raw


class _FakeSessions:
    def __init__(self) -> None:
        self.statuses: list[AuditStatus] = []
        self.customer_id: str | None = None

    async def set_status(self, session_id: str, status: AuditStatus) -> None:
        self.statuses.append(status)

    async def set_customer_id(self, session_id: str, google_customer_id: str) -> None:
        self.customer_id = google_customer_id


class _FakeReportRepo:
    async def create(self, **kw: object) -> WasteReport:
        return WasteReport(
            id="rep-9",
            window_start=kw["window_start"],  # type: ignore[arg-type]
            window_end=kw["window_end"],  # type: ignore[arg-type]
            total_spend_micros=kw["total_spend_micros"],  # type: ignore[arg-type]
            headline_waste_micros=kw["headline_waste_micros"],  # type: ignore[arg-type]
            measurement_gap_pct=kw["measurement_gap_pct"],  # type: ignore[arg-type]
            confidence=kw["confidence"],  # type: ignore[arg-type]
        )


class _FakeFindingRepo:
    def __init__(self) -> None:
        self.added: list[dict[str, object]] = []

    async def add(self, **kw: object) -> None:
        self.added.append(kw)


def _campaign(cost: int) -> CampaignSnapshot:
    return CampaignSnapshot(
        id="c",
        account_id="acc",
        snapshot_date=_D,
        campaign_id=1,
        name="C",
        status="ENABLED",
        channel_type="SEARCH",
        budget_micros=100 * _M,
        bidding_strategy="MANUAL_CPC",
        impressions=1000,
        clicks=100,
        cost_micros=cost,
        conversions=0.0,
        conv_value=0.0,
    )


def _term(term: str, clicks: int, conv: float, cost: int) -> SearchTermSnapshot:
    return SearchTermSnapshot(
        id="t",
        account_id="acc",
        snapshot_date=_D,
        search_term=term,
        ad_group_id=1,
        impressions=clicks * 10,
        clicks=clicks,
        cost_micros=cost,
        conversions=conv,
        matched_keyword_id=None,
    )


def _compute() -> ComputeAndStoreWasteReportUseCase:
    return ComputeAndStoreWasteReportUseCase(_FakeReportRepo(), _FakeFindingRepo())


async def test_scan_happy_path_marks_ready_persists_and_discovers_customer() -> None:
    raw = AuditRawData(
        campaigns=[_campaign(10_000 * _M)],
        search_terms=[_term("kurs za darmo", clicks=20, conv=0, cost=200 * _M)],
        keywords=[],
        conversion_actions=[],
    )
    reader = _FakeReader(customers=["customers/1234567890"], raw=raw)
    sessions = _FakeSessions()

    report_id = await RunAuditScanUseCase(reader, sessions, _compute()).execute(
        audit_session_id="sess-1", refresh_token="rt", today=_D, days=30
    )

    assert report_id == "rep-9"
    assert sessions.customer_id == "1234567890"  # resource name normalised
    assert sessions.statuses == [AuditStatus.SCANNING, AuditStatus.READY]
    assert reader.pulled == ("1234567890", 30)


async def test_scan_no_accessible_customers_marks_failed() -> None:
    reader = _FakeReader(customers=[], raw=AuditRawData([], [], [], []))
    sessions = _FakeSessions()

    result = await RunAuditScanUseCase(reader, sessions, _compute()).execute(
        audit_session_id="s", refresh_token="rt", today=_D
    )

    assert result is None
    assert sessions.statuses == [AuditStatus.FAILED]
