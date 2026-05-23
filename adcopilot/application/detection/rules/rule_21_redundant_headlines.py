"""Detection rule: RSA ad contains multiple headlines that say essentially the
same thing — wasting precious headline slots the algorithm could use to test
genuinely different messaging angles.

When several headlines share >60% word-token overlap (Jaccard similarity),
Google's algorithm is effectively rotating near-identical copy, which
reduces creative diversity, limits learning, and hurts ad strength score.
"""

from __future__ import annotations

import json
import re
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

_RSA_TYPE = "RESPONSIVE_SEARCH_AD"
_MIN_IMPRESSIONS = 100
_JACCARD_THRESHOLD = 0.60  # Headlines more similar than this are "redundant"
_MIN_REDUNDANT = 3  # Flag only when ≥ 3 headlines are redundant


def _tokenise(text: str) -> frozenset[str]:
    return frozenset(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    union = a | b
    if not union:
        return 1.0
    return len(a & b) / len(union)


class RedundantHeadlinesRule:
    kind = RecommendationKind.REDUNDANT_HEADLINES
    severity = RecommendationSeverity.LOW

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        recs: list[Recommendation] = []

        for ad in ctx.ads:
            if ad.status != "ENABLED":
                continue
            if _RSA_TYPE not in ad.type.upper():
                continue
            if ad.impressions < _MIN_IMPRESSIONS:
                continue

            try:
                headlines: list[str] = json.loads(ad.headlines_json)
            except (json.JSONDecodeError, TypeError):
                continue

            if len(headlines) < _MIN_REDUNDANT:
                continue

            token_sets = [_tokenise(h) for h in headlines]

            # Count how many headlines are "too similar" to at least one other
            redundant_indices: set[int] = set()
            for i in range(len(token_sets)):
                for j in range(i + 1, len(token_sets)):
                    if not token_sets[i] or not token_sets[j]:
                        continue
                    if _jaccard(token_sets[i], token_sets[j]) >= _JACCARD_THRESHOLD:
                        redundant_indices.add(i)
                        redundant_indices.add(j)

            if len(redundant_indices) < _MIN_REDUNDANT:
                continue

            redundant_headlines = [headlines[i] for i in sorted(redundant_indices)]
            target = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            payload = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            evidence = {
                "ad_id": ad.ad_id,
                "total_headlines": len(headlines),
                "redundant_headline_count": len(redundant_indices),
                "redundant_headlines": redundant_headlines[:5],
                "impressions": ad.impressions,
            }
            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target=target,
                    payload=payload,
                    evidence=evidence,
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
