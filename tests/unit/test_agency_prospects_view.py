"""Unit tests for build_prospects_view (Phase 5C — pure)."""

from __future__ import annotations

from types import SimpleNamespace

from adcopilot.application.use_cases.agency_prospects import build_prospects_view
from adcopilot.domain.agency import Prospect, ProspectStatus

_M = 1_000_000


def _prospect(**kw: object) -> Prospect:
    base = {"id": "p1", "organization_id": "o1", "customer_id": "111", "name": "Acme"}
    base.update(kw)
    return Prospect(**base)  # type: ignore[arg-type]


def test_view_includes_waste_when_report_present() -> None:
    audited = _prospect(status=ProspectStatus.AUDITED, report_id="r1")
    report = SimpleNamespace(
        headline_waste_micros=2_000 * _M, annual_waste_micros=24_000 * _M, currency="PLN"
    )

    rows = build_prospects_view([audited], {"r1": report})

    assert rows[0]["status"] == "audited"
    assert rows[0]["headline_waste_micros"] == 2_000 * _M
    assert rows[0]["annual_waste_micros"] == 24_000 * _M
    assert rows[0]["currency"] == "PLN"


def test_view_nulls_waste_when_no_report() -> None:
    fresh = _prospect(status=ProspectStatus.NEW)  # no report_id

    rows = build_prospects_view([fresh], {})

    assert rows[0]["status"] == "new"
    assert rows[0]["headline_waste_micros"] is None
    assert rows[0]["report_id"] is None
