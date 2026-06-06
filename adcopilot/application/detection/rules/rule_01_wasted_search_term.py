"""Detection rule: flag search terms that consume budget with zero conversions and match waste signals."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

# Junk-intent signal words/phrases. The product serves the Polish market, so
# the original English-only list almost never matched real Polish search terms,
# leaving this rule effectively dead on PL accounts. Polish terms come first,
# English ones are kept for mixed-language accounts. Matched as a
# case-insensitive substring, so multi-word phrases are fine. Conservative and
# extendable.
_WASTE_SIGNALS = [
    # Polish — "free / for free"
    "darmowy",
    "darmowe",
    "darmowa",
    "darmo",
    "za darmo",
    "bezpłatny",
    "bezpłatne",
    "gratis",
    # Polish — job seekers (not customers)
    "praca",
    "oferty pracy",
    "zarobki",
    "wynagrodzenie",
    "pensja",
    # Polish — research / how-to / informational intent
    "jak zrobić",
    "jak działa",
    "instrukcja",
    "przepis",
    "definicja",
    "co to jest",
    "opinie",
    "forum",
    "wzór",
    # English — kept for mixed-language accounts
    "free",
    "jobs",
    "salary",
    "how to",
    "diy",
    "wikipedia",
    "youtube",
]


class WastedSearchTermRule:
    kind = RecommendationKind.ADD_NEGATIVE_KEYWORD
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []
        # Anchor the waste floor to the client's target CPA when configured
        # (30% of an acceptable conversion cost); else 30% of historical avg CPA.
        econ = ctx.business_economics
        if econ is not None and getattr(econ, "target_cpa", None):
            basis_micros = int(econ.target_cpa * 1_000_000)
        else:
            basis_micros = ctx.history.avg_cpa_micros
        avg_cpa = ctx.history.avg_cpa_micros
        cost_threshold = basis_micros * 0.3

        for st in ctx.search_terms:
            if st.clicks < 5:
                continue
            if st.conversions != 0:
                continue
            if st.cost_micros <= cost_threshold:
                continue

            # Signal words are a booster, not a hard gate: the cost/zero-conv
            # criteria are the primary trigger. We still require either a
            # junk-intent signal OR egregious waste — spending more than a full
            # acceptable conversion cost (one whole CPA) with zero conversions
            # is strong evidence of waste regardless of the wording.
            term_lower = st.search_term.lower()
            has_signal = any(signal in term_lower for signal in _WASTE_SIGNALS)
            egregious = st.cost_micros > basis_micros
            if not (has_signal or egregious):
                continue

            target = {"ad_group_id": st.ad_group_id, "search_term": st.search_term}
            payload = {
                "negative_keyword": st.search_term,
                "level": "AD_GROUP",
                "match_type": "EXACT",
            }
            evidence = {
                "search_term": st.search_term,
                "clicks": st.clicks,
                "cost_micros": st.cost_micros,
                "conversions": 0,
                "avg_cpa_micros": avg_cpa,
            }
            recs.append(
                self._make_rec(
                    account_id=ctx.account.id,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=st.cost_micros,
                )
            )

        return recs

    def _make_rec(
        self,
        account_id: str,
        target: dict[str, Any],
        payload: dict[str, Any],
        evidence: dict[str, Any],
        estimated_monthly_savings_micros: int,
    ) -> Recommendation:
        return Recommendation(
            id=RecommendationId(str(uuid.uuid4())),
            account_id=account_id,  # type: ignore[arg-type]
            kind=self.kind,
            severity=self.severity,
            target=target,
            payload=payload,
            evidence=evidence,
            estimated_monthly_savings_micros=estimated_monthly_savings_micros,
            created_at=datetime.now(tz=UTC),
            status=RecommendationStatus.PENDING,
        )
