"""Map a read-only Google Ads pull to the engine's AuditDataset (T2.1, pure).

Kept free of I/O so it is fully unit-testable: given the windowed snapshot rows
the scan reader returns, produce the ``AuditDataset`` the waste engine consumes.
"""

from __future__ import annotations

from datetime import date

from adcopilot.application.audit.scan_reader import AuditRawData
from adcopilot.application.audit.vertical_inference import infer_vertical
from adcopilot.application.audit.waste_engine import AuditDataset, KeywordRow, SearchTermRow

# A campaign losing more than this share of impressions to budget is a flagged
# "issue" (budget-constrained) in the Tier-3 issue count.
_BUDGET_LOST_IS_THRESHOLD = 0.10


def build_audit_dataset(
    raw: AuditRawData,
    *,
    window_start: date,
    window_end: date,
    days: int,
    vertical: str | None = None,
    city: str | None = None,
) -> AuditDataset:
    total_spend_micros = sum(c.cost_micros for c in raw.campaigns)

    # criterion id -> keyword text, so a search term can be deduped against the
    # keyword it matched (the engine dedups by keyword text).
    keyword_text_by_id = {k.criterion_id: k.text for k in raw.keywords}
    search_terms = [
        SearchTermRow(
            term=s.search_term,
            clicks=s.clicks,
            conversions=s.conversions,
            cost_micros=s.cost_micros,
            matched_keyword=(
                keyword_text_by_id.get(s.matched_keyword_id)
                if s.matched_keyword_id is not None
                else None
            ),
        )
        for s in raw.search_terms
    ]
    keywords = [
        KeywordRow(
            text=k.text,
            clicks=k.clicks,
            conversions=k.conversions,
            cost_micros=k.cost_micros,
            quality_score=k.quality_score,
            avg_cpc_micros=k.avg_cpc_micros,
        )
        for k in raw.keywords
    ]

    # Measurement gap (conservative & honest): if the account has no enabled
    # conversion action counted in the "Conversions" column, it cannot measure
    # return at all. A finer per-source figure needs GA4 reconciliation (Phase 4).
    has_tracking = any(
        c.status == "ENABLED" and c.include_in_conversions_metric for c in raw.conversion_actions
    )
    measurement_gap_pct = 0.0 if has_tracking else 1.0

    issues_count = sum(
        1
        for c in raw.campaigns
        if c.search_budget_lost_impression_share is not None
        and c.search_budget_lost_impression_share > _BUDGET_LOST_IS_THRESHOLD
    )

    return AuditDataset(
        window_start=window_start,
        window_end=window_end,
        total_spend_micros=total_spend_micros,
        search_terms=search_terms,
        keywords=keywords,
        vertical=vertical
        or infer_vertical([c.name for c in raw.campaigns] + [k.text for k in raw.keywords]),
        city=city,
        measurement_gap_pct=measurement_gap_pct,
        issues_count=issues_count,
        days_of_data=days,
    )
