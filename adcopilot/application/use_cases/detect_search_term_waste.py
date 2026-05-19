"""DetectSearchTermWasteUseCase — fires SEARCH_TERM_WASTE for terms >20% daily budget with 0 conversions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.domain.snapshot import SearchTermSnapshot

logger = structlog.get_logger(__name__)

_WASTE_THRESHOLD = 0.20  # >20% of total daily cost with zero conversions


def detect_search_term_waste(
    account_id: AccountId,
    search_terms: list[SearchTermSnapshot],
) -> list[Recommendation]:
    """Return SEARCH_TERM_WASTE recommendations for wasteful search terms.

    A term is wasteful if it consumed > 20% of the total daily spend (sum of
    cost_micros across all terms in the snapshot) with zero conversions.
    """
    total_cost = sum(s.cost_micros for s in search_terms)
    if total_cost == 0:
        return []

    recs: list[Recommendation] = []
    now = datetime.now(UTC)

    for term in search_terms:
        if term.conversions > 0:
            continue
        if term.cost_micros / total_cost <= _WASTE_THRESHOLD:
            continue

        recs.append(
            Recommendation(
                id=RecommendationId(str(uuid.uuid4())),
                account_id=account_id,
                kind=RecommendationKind.SEARCH_TERM_WASTE,
                severity=RecommendationSeverity.HIGH,
                target={"account_id": str(account_id)},
                payload={"search_term": term.search_term, "action": "block"},
                evidence={
                    "search_term": term.search_term,
                    "cost_micros": term.cost_micros,
                    "total_cost_micros": total_cost,
                    "waste_pct": round(term.cost_micros / total_cost * 100, 1),
                    "conversions": 0,
                    "campaign_name": term.campaign_name,
                },
                estimated_monthly_savings_micros=term.cost_micros * 30,
                created_at=now,
                status=RecommendationStatus.PENDING,
            )
        )
        logger.info(
            "search_term_waste.detected",
            account_id=str(account_id),
            term=term.search_term,
            waste_pct=round(term.cost_micros / total_cost * 100, 1),
        )

    return recs
