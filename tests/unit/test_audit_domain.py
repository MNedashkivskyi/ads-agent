"""Unit tests for the audit-funnel domain and repository mappers (Phase 0 / T0.1)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from adcopilot.domain.audit import (
    HEADLINE_CATEGORIES,
    AuditSession,
    AuditSource,
    AuditStatus,
    FindingTier,
    ReportConfidence,
    WasteCategory,
    WasteReport,
)
from adcopilot.infrastructure.db.models import (
    AuditSessionModel,
    RecoveryLedgerModel,
    WasteFindingModel,
    WasteReportModel,
)
from adcopilot.infrastructure.db.repositories.audit_repository import (
    finding_to_domain,
    recovery_to_domain,
    report_to_domain,
    session_to_domain,
)


def _report(total: int, headline: int) -> WasteReport:
    return WasteReport(
        id="r1",
        window_start=date(2026, 5, 1),
        window_end=date(2026, 5, 31),
        total_spend_micros=total,
        headline_waste_micros=headline,
        measurement_gap_pct=0.0,
        confidence=ReportConfidence.HIGH,
    )


def test_annual_waste_is_twelve_times_headline() -> None:
    assert _report(0, 3_400_000).annual_waste_micros == 40_800_000


def test_waste_pct_normal() -> None:
    assert abs(_report(total=10_000_000, headline=1_800_000).waste_pct - 0.18) < 1e-9


def test_waste_pct_zero_spend_is_zero() -> None:
    assert _report(total=0, headline=500_000).waste_pct == 0.0


def test_session_is_expired() -> None:
    now = datetime(2026, 6, 17, tzinfo=UTC)
    assert AuditSession(
        id="s", google_customer_id="123", expires_at=now - timedelta(seconds=1)
    ).is_expired(now=now)
    assert not AuditSession(
        id="s", google_customer_id="123", expires_at=now + timedelta(days=1)
    ).is_expired(now=now)
    assert not AuditSession(id="s", google_customer_id="123").is_expired(now=now)


def test_session_is_promoted_when_user_set() -> None:
    assert AuditSession(id="s", google_customer_id="123", user_id="u1").is_promoted
    assert not AuditSession(id="s", google_customer_id="123").is_promoted


def test_headline_categories_are_the_three_tier1() -> None:
    assert {
        WasteCategory.SEARCHTERM_WASTE,
        WasteCategory.KEYWORD_WASTE,
        WasteCategory.NEGATIVE_BLOCKABLE,
    } == HEADLINE_CATEGORIES
    # estimated / qualitative categories must never feed the headline.
    assert WasteCategory.MEASUREMENT_GAP not in HEADLINE_CATEGORIES
    assert WasteCategory.QS_OVERPAYMENT not in HEADLINE_CATEGORIES


def test_session_mapper_roundtrip() -> None:
    sid, uid = uuid.uuid4(), uuid.uuid4()
    s = session_to_domain(
        AuditSessionModel(
            id=sid,
            google_customer_id="123-456-7890",
            status="promoted",
            oauth_scope="adwords-readonly",
            source="landing",
            email="x@example.com",
            user_id=uid,
            account_id=None,
            consent_at=None,
            created_at=None,
            expires_at=None,
        )
    )
    assert s.id == str(sid)
    assert s.status is AuditStatus.PROMOTED
    assert s.source is AuditSource.LANDING
    assert s.user_id == str(uid)
    assert s.account_id is None
    assert s.is_promoted


def test_finding_mapper_preserves_evidence_dict() -> None:
    rid = uuid.uuid4()
    evidence = {"terms": ["buty tanie", "buty allegro"], "clicks": 42, "cost_micros": 1_800_000}
    f = finding_to_domain(
        WasteFindingModel(
            id=uuid.uuid4(),
            report_id=rid,
            category="searchterm_waste",
            tier="confirmed",
            title="Zmarnowany budżet na frazy",
            severity="HIGH",
            amount_micros=1_800_000,
            evidence=evidence,
            recommendation_id=None,
        )
    )
    assert f.category is WasteCategory.SEARCHTERM_WASTE
    assert f.tier is FindingTier.CONFIRMED
    assert f.amount_micros == 1_800_000
    assert f.evidence == evidence
    assert f.report_id == str(rid)


def test_report_mapper_roundtrip() -> None:
    r = report_to_domain(
        WasteReportModel(
            id=uuid.uuid4(),
            audit_session_id=None,
            account_id=None,
            window_start=date(2026, 5, 1),
            window_end=date(2026, 5, 31),
            currency="PLN",
            total_spend_micros=10_000_000,
            headline_waste_micros=1_800_000,
            measurement_gap_pct=0.6,
            confidence="high",
            methodology_version="1",
            computed_at=None,
        )
    )
    assert r.confidence is ReportConfidence.HIGH
    assert r.annual_waste_micros == 21_600_000
    assert abs(r.waste_pct - 0.18) < 1e-9
    assert abs(r.measurement_gap_pct - 0.6) < 1e-9


def test_recovery_mapper_roundtrip() -> None:
    aid = uuid.uuid4()
    e = recovery_to_domain(
        RecoveryLedgerModel(
            id=uuid.uuid4(),
            account_id=aid,
            finding_id=None,
            recommendation_id=None,
            applied_at=datetime(2026, 6, 1, tzinfo=UTC),
            method="measured",
            baseline_metric={"cpa_micros": 50_000_000},
            realized_saving_micros=260_000,
            measured_at=datetime(2026, 6, 15, tzinfo=UTC),
        )
    )
    assert e.account_id == str(aid)
    assert e.method == "measured"
    assert e.realized_saving_micros == 260_000
    assert e.baseline_metric == {"cpa_micros": 50_000_000}
