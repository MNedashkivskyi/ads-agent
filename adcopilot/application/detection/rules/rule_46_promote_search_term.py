"""Rule 46 — Promote High-Converting Search Term.

Fires when a search term has ≥3 conversions, CPA ≤ 120% of account average,
and ≥5 clicks, but is NOT already added as a keyword.  Recommends adding the
term as an EXACT-match keyword in the ad group it already triggers.

Fuzzy matching (Jaccard similarity on token sets ≥ 0.8) prevents suggesting
terms that are essentially duplicates of existing keywords.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_MIN_CONVERSIONS = 3
_MIN_CLICKS = 5
_CPA_MULTIPLIER = 1.2   # allow up to 120% of account average CPA
_JACCARD_THRESHOLD = 0.8


def _jaccard(a: str, b: str) -> float:
    """Token-level Jaccard similarity between two strings."""
    ta = set(a.lower().split())
    tb = set(b.lower().split())
    if not ta and not tb:
        return 1.0
    union = ta | tb
    return len(ta & tb) / len(union)


def _is_already_keyword(search_term: str, keyword_texts: list[str]) -> bool:
    """Return True if *search_term* is too similar to any existing keyword."""
    st_lower = search_term.lower().strip()
    for kw in keyword_texts:
        if _jaccard(st_lower, kw.lower().strip()) >= _JACCARD_THRESHOLD:
            return True
    return False


class PromoteSearchTermRule:
    kind = RecommendationKind.PROMOTE_SEARCH_TERM
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.search_terms:
            return []

        existing_kw_texts = [kw.text for kw in ctx.keywords]
        max_cpa = (
            int(ctx.history.avg_cpa_micros * _CPA_MULTIPLIER)
            if ctx.history.avg_cpa_micros > 0
            else 10_000_000_000  # no upper bound when avg unknown
        )

        recs: list[Recommendation] = []
        seen_terms: set[str] = set()

        for st in ctx.search_terms:
            term = st.search_term.strip()
            if term in seen_terms:
                continue

            if st.conversions < _MIN_CONVERSIONS:
                continue
            if st.clicks < _MIN_CLICKS:
                continue

            # CPA check
            if st.conversions > 0:
                cpa = int(st.cost_micros / st.conversions)
                if cpa > max_cpa:
                    continue

            if _is_already_keyword(term, existing_kw_texts):
                continue

            seen_terms.add(term)
            cpa_micros = int(st.cost_micros / st.conversions) if st.conversions > 0 else 0

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={
                        "ad_group_id": st.ad_group_id,
                        "search_term": term,
                    },
                    payload={
                        "search_term": term,
                        "suggested_match_type": "EXACT",
                        "suggested_ad_group_id": st.ad_group_id,
                        "conversions": st.conversions,
                        "cpa_micros": cpa_micros,
                    },
                    evidence={
                        "search_term": term,
                        "clicks": st.clicks,
                        "conversions": st.conversions,
                        "cost_micros": st.cost_micros,
                        "cpa_micros": cpa_micros,
                        "ad_group_id": st.ad_group_id,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
