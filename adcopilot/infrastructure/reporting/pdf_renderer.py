"""PDF renderer for performance reports using reportlab."""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
MARGIN = 50
FOOTER_TEXT = "Wygenerowano przez Adswise - adswise.pl"


def _draw_footer(c: canvas.Canvas, page_num: int) -> None:
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    c.drawString(MARGIN, 30, FOOTER_TEXT)
    c.drawRightString(PAGE_W - MARGIN, 30, f"Strona {page_num}")
    c.setFillColorRGB(0, 0, 0)


def _draw_title(c: canvas.Canvas, text: str, y: float, font_size: int = 16) -> float:
    c.setFont("Helvetica-Bold", font_size)
    c.drawString(MARGIN, y, text)
    return y - font_size - 8


def _draw_body(c: canvas.Canvas, text: str, y: float, font_size: int = 10, max_width: float = PAGE_W - 2 * MARGIN) -> float:
    c.setFont("Helvetica", font_size)
    words = text.split()
    line = ""
    for word in words:
        test_line = (line + " " + word).strip()
        if c.stringWidth(test_line, "Helvetica", font_size) <= max_width:
            line = test_line
        else:
            c.drawString(MARGIN, y, line)
            y -= font_size + 4
            line = word
            if y < 60:
                break
    if line:
        c.drawString(MARGIN, y, line)
        y -= font_size + 4
    return y


def _delta_str(current, previous) -> str:
    """Return a plain ASCII delta string like +5.2% or -3.1."""
    if current is None or previous is None:
        return "brak danych"
    try:
        diff = float(current) - float(previous)
        sign = "+" if diff >= 0 else ""
        return f"{sign}{diff:.2f}"
    except (TypeError, ValueError):
        return "brak danych"


def render_performance_report_pdf(report_data: dict) -> bytes:
    """Render a performance report as PDF bytes."""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)

    metrics = report_data.get("metrics", {})
    comparison = report_data.get("comparison", {})
    top_recs = report_data.get("top_recommendations", [])
    qs_summary = report_data.get("qs_plan_summary", {})
    summary_pl = report_data.get("summary_pl", "")
    account_id = report_data.get("account_id", "")
    period_start = report_data.get("period_start", "")
    period_end = report_data.get("period_end", "")
    generated_at = report_data.get("generated_at", "")

    # ------------------------------------------------------------------
    # Page 1: Title page
    # ------------------------------------------------------------------
    y = PAGE_H - MARGIN
    c.setFont("Helvetica-Bold", 22)
    c.drawString(MARGIN, y, "Raport Wydajnosci Google Ads")
    y -= 40

    c.setFont("Helvetica", 12)
    c.drawString(MARGIN, y, f"Konto: {account_id}")
    y -= 20
    c.drawString(MARGIN, y, f"Okres: {period_start} - {period_end}")
    y -= 20
    c.drawString(MARGIN, y, f"Wygenerowano: {generated_at}")

    _draw_footer(c, 1)
    c.showPage()

    # ------------------------------------------------------------------
    # Page 2: Executive summary + KPI boxes
    # ------------------------------------------------------------------
    y = PAGE_H - MARGIN
    y = _draw_title(c, "Podsumowanie Zarzadcze", y, 16)
    y -= 10

    if summary_pl:
        y = _draw_body(c, summary_pl, y, font_size=10)

    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(MARGIN, y, "Kluczowe wskazniki (KPI):")
    y -= 20

    kpis = [
        ("Wydatki (PLN)", metrics.get("spend_pln"), comparison.get("spend_pln")),
        ("Klikniecia", metrics.get("clicks"), comparison.get("clicks")),
        ("Konwersje", metrics.get("conversions"), comparison.get("conversions")),
        ("CTR (%)", metrics.get("ctr"), comparison.get("ctr")),
        ("CPA (PLN)", metrics.get("cpa"), comparison.get("cpa")),
    ]

    c.setFont("Helvetica", 10)
    for label, current, previous in kpis:
        delta = _delta_str(current, previous)
        val_str = str(current) if current is not None else "brak danych"
        c.drawString(MARGIN, y, f"{label}: {val_str}   (zmiana vs poprzedni okres: {delta})")
        y -= 18
        if y < 60:
            break

    _draw_footer(c, 2)
    c.showPage()

    # ------------------------------------------------------------------
    # Page 3: Executed actions (top recommendations)
    # ------------------------------------------------------------------
    y = PAGE_H - MARGIN
    y = _draw_title(c, "Wykonane Dzialania", y, 16)
    y -= 10

    if not top_recs:
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, y, "Brak wykonanych dzialan w tym okresie.")
        y -= 20
    else:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, "Rodzaj dzialania")
        c.drawString(MARGIN + 300, y, "Szacowane oszczednosci (PLN)")
        y -= 16
        c.setFont("Helvetica", 10)
        for rec in top_recs:
            kind = rec.get("kind", "")
            savings = rec.get("estimated_savings_pln", 0)
            c.drawString(MARGIN, y, kind)
            c.drawString(MARGIN + 300, y, str(savings))
            y -= 16
            if y < 60:
                break

    _draw_footer(c, 3)
    c.showPage()

    # ------------------------------------------------------------------
    # Page 4: QS plan status
    # ------------------------------------------------------------------
    y = PAGE_H - MARGIN
    y = _draw_title(c, "Status Planow QS", y, 16)
    y -= 10

    if not qs_summary:
        c.setFont("Helvetica", 10)
        c.drawString(MARGIN, y, "Brak planow QS dla tego konta.")
        y -= 20
    else:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, y, "Status")
        c.drawString(MARGIN + 200, y, "Liczba planow")
        y -= 16
        c.setFont("Helvetica", 10)
        for status, count in qs_summary.items():
            c.drawString(MARGIN, y, str(status))
            c.drawString(MARGIN + 200, y, str(count))
            y -= 16
            if y < 60:
                break

    _draw_footer(c, 4)
    c.showPage()

    # ------------------------------------------------------------------
    # Page 5: Next steps
    # ------------------------------------------------------------------
    y = PAGE_H - MARGIN
    y = _draw_title(c, "Nastepne Kroki", y, 16)
    y -= 20

    next_steps = (
        "Adswise automatycznie monitoruje Twoje kampanie. "
        "Kolejny raport zostanie wygenerowany automatycznie. "
        "W razie pytan skontaktuj sie z nami przez panel uzytkownika lub Telegrama."
    )
    _draw_body(c, next_steps, y, font_size=11)

    _draw_footer(c, 5)
    c.showPage()

    c.save()
    return buf.getvalue()
