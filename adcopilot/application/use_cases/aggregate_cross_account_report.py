"""Cross-account report aggregation (Phase 3 / T3.3).

Pure helpers to combine per-account performance metrics into a single
portfolio-level summary, plus a branding container. Kept I/O-free so the
aggregation is unit-testable; the endpoint wires it to the per-account report
generator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReportBranding:
    """Light branding for Business reports."""

    company_name: str = ""
    logo_url: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"company_name": self.company_name, "logo_url": self.logo_url}


def aggregate_metrics(per_account_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    """Sum additive metrics across accounts and recompute derived ones.

    Expects each dict to carry ``spend_pln``, ``clicks``, ``impressions`` and
    ``conversions`` (the per-account report shape). Derived ``cpa`` and ``ctr``
    are recomputed from the portfolio totals; ``roas`` is left ``None`` unless
    revenue is present.
    """
    spend = sum(float(m.get("spend_pln") or 0) for m in per_account_metrics)
    clicks = sum(int(m.get("clicks") or 0) for m in per_account_metrics)
    impressions = sum(int(m.get("impressions") or 0) for m in per_account_metrics)
    conversions = sum(float(m.get("conversions") or 0) for m in per_account_metrics)

    cpa = round(spend / conversions, 2) if conversions > 0 else None
    ctr = round(clicks / impressions * 100, 2) if impressions > 0 else None

    return {
        "spend_pln": round(spend, 2),
        "clicks": clicks,
        "impressions": impressions,
        "conversions": round(conversions, 2),
        "cpa": cpa,
        "ctr": ctr,
        "roas": None,
        "account_count": len(per_account_metrics),
    }


def build_cross_account_report(
    per_account: list[dict[str, Any]],
    branding: ReportBranding,
    *,
    period_start: str,
    period_end: str,
) -> dict[str, Any]:
    """Assemble the portfolio report payload from per-account report dicts."""
    totals = aggregate_metrics([r.get("metrics", {}) for r in per_account])
    return {
        "period_start": period_start,
        "period_end": period_end,
        "branding": branding.as_dict(),
        "totals": totals,
        "accounts": [
            {
                "account_id": r.get("account_id"),
                "metrics": r.get("metrics"),
                "summary_pl": r.get("summary_pl"),
            }
            for r in per_account
        ],
    }
