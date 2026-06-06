"""ADW-015: performance-report PDF renders Polish diacritics with a bundled font."""

from __future__ import annotations

import pytest

pytest.importorskip("reportlab")


def test_unicode_font_is_registered() -> None:
    from reportlab.pdfbase import pdfmetrics

    from adcopilot.infrastructure.reporting import pdf_renderer  # noqa: F401

    names = pdfmetrics.getRegisteredFontNames()
    assert "AdswiseSans" in names
    assert "AdswiseSans-Bold" in names


def test_font_files_are_bundled() -> None:
    from adcopilot.infrastructure.reporting.pdf_renderer import _FONTS_DIR

    assert (_FONTS_DIR / "DejaVuSans.ttf").exists()
    assert (_FONTS_DIR / "DejaVuSans-Bold.ttf").exists()


def test_renders_polish_summary_without_error() -> None:
    from adcopilot.infrastructure.reporting.pdf_renderer import render_performance_report_pdf

    pdf = render_performance_report_pdf(
        {
            "account_id": "123",
            "period_start": "2026-05-01",
            "period_end": "2026-05-31",
            "generated_at": "2026-06-01",
            # Polish diacritics that Helvetica could not render.
            "summary_pl": "Wydajność wzrosła. Zażółć gęślą jaźń — ćma, łąka, źdźbło.",
            "metrics": {"spend_pln": 1234.5, "clicks": 100, "conversions": 5, "ctr": 2.1, "cpa": 246.9},
            "comparison": {},
            "top_recommendations": [{"kind": "ADD_NEGATIVE_KEYWORD", "estimated_savings_pln": 184}],
            "qs_plan_summary": {"COMPLETED": 2},
        }
    )
    assert isinstance(pdf, bytes)
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 1000
