"""Agency prospects dashboard view (Phase 5C — pure).

Maps prospects plus their latest waste reports into dashboard rows (status + the
headline waste the audit found). Kept I/O-free so it's unit-testable; the endpoint
wires it to the repos.
"""

from __future__ import annotations

from typing import Any

from adcopilot.domain.agency import Prospect


def build_prospects_view(
    prospects: list[Prospect], report_by_id: dict[str, Any]
) -> list[dict[str, object]]:
    """One row per prospect: identity + status + waste (when a report exists)."""
    rows: list[dict[str, object]] = []
    for p in prospects:
        report = report_by_id.get(p.report_id) if p.report_id else None
        rows.append(
            {
                "id": p.id,
                "customer_id": p.customer_id,
                "name": p.name,
                "status": p.status.value,
                "report_id": p.report_id,
                "headline_waste_micros": report.headline_waste_micros if report else None,
                "annual_waste_micros": report.annual_waste_micros if report else None,
                "currency": report.currency if report else None,
            }
        )
    return rows
