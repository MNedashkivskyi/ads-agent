"""Unit test for render_waste_audit_pdf (Audit Funnel T2.3)."""

from __future__ import annotations

from adcopilot.infrastructure.reporting.pdf_renderer import render_waste_audit_pdf


def test_renders_pdf_bytes() -> None:
    pdf = render_waste_audit_pdf(
        {
            "headline_waste_pln": 3400,
            "annual_waste_pln": 40800,
            "waste_pct": 0.18,
            "measurement_gap_pct": 0.6,
            "confidence": "medium",
            "customer_id": "123-456-7890",
            "period": "2026-05-01 — 2026-05-31",
            "findings": [
                {"title": "Zmarnowany budżet na frazy", "amount_pln": 1800, "tier": "confirmed"},
                {"title": "Zawyżone CPC", "amount_pln": 700, "tier": "estimated"},
                {"title": "Luka w pomiarze konwersji", "amount_pln": None, "tier": "qualitative"},
            ],
        }
    )
    assert pdf[:4] == b"%PDF"
    assert len(pdf) > 800


def test_renders_pdf_with_no_findings() -> None:
    pdf = render_waste_audit_pdf(
        {
            "headline_waste_pln": 0,
            "annual_waste_pln": 0,
            "waste_pct": 0,
            "confidence": "limited",
            "findings": [],
        }
    )
    assert pdf[:4] == b"%PDF"
