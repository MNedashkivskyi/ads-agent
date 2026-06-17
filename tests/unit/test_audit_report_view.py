"""Unit tests for preview_findings (Audit Funnel T2.2)."""

from __future__ import annotations

from adcopilot.application.audit.report_view import preview_findings
from adcopilot.domain.audit import FindingTier, WasteCategory, WasteFinding

_M = 1_000_000


def _f(category: WasteCategory, amount: int | None) -> WasteFinding:
    return WasteFinding(
        id="x",
        report_id="r",
        category=category,
        tier=FindingTier.CONFIRMED if amount is not None else FindingTier.QUALITATIVE,
        title=str(category.value),
        amount_micros=amount,
    )


def test_preview_returns_top_by_amount_and_withheld_count() -> None:
    findings = [
        _f(WasteCategory.SEARCHTERM_WASTE, 300 * _M),
        _f(WasteCategory.NEGATIVE_BLOCKABLE, 500 * _M),
        _f(WasteCategory.KEYWORD_WASTE, 100 * _M),
        _f(WasteCategory.QS_OVERPAYMENT, 80 * _M),
        _f(WasteCategory.MEASUREMENT_GAP, None),
    ]
    shown, withheld = preview_findings(findings, limit=3)
    assert [f.amount_micros for f in shown] == [500 * _M, 300 * _M, 100 * _M]
    assert withheld == 2


def test_preview_orders_qualitative_last() -> None:
    findings = [
        _f(WasteCategory.MEASUREMENT_GAP, None),
        _f(WasteCategory.SEARCHTERM_WASTE, 50 * _M),
    ]
    shown, withheld = preview_findings(findings, limit=1)
    assert shown[0].amount_micros == 50 * _M
    assert withheld == 1
