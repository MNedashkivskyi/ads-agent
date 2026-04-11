"""Detection rule: top keywords in an ad group share little or no token overlap
with the ad headlines — the ads are not tailored to what people search for.

This hurts Quality Score (Expected CTR component) and wastes budget on
clicks that are unlikely to convert because the ad message doesn't match
search intent.
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

# Minimum token coverage: at least this fraction of the top-keyword tokens
# must appear in ANY headline for the ad group to be considered relevant.
_MIN_COVERAGE = 0.35
# Number of top keywords (by impressions) to represent the ad group's theme
_TOP_K_KEYWORDS = 5
# Ad group must have this many impressions to have statistical meaning
_MIN_IMPRESSIONS = 200
# Only flag RSA ads; ETAs and other types have no headlines list to analyse
_RSA_TYPE = "RESPONSIVE_SEARCH_AD"
# Stop-words that carry no semantic meaning and should be ignored
_STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "can", "your", "our",
    "their", "its", "we", "you", "i", "it", "this", "that", "these",
    "those", "not", "no", "so", "if", "up", "out", "about",
}


def _tokenise(text: str) -> set[str]:
    """Lowercase, strip punctuation, remove stop-words."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in _STOP_WORDS and len(t) > 1}


class AdKeywordMismatchRule:
    kind = RecommendationKind.AD_KEYWORD_MISMATCH
    severity = RecommendationSeverity.HIGH

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        # Index ads and keywords by ad group
        ads_by_ag: dict[int, list] = {}
        for ad in ctx.ads:
            if ad.status == "ENABLED" and _RSA_TYPE in ad.type.upper():
                ads_by_ag.setdefault(ad.ad_group_id, []).append(ad)

        kws_by_ag: dict[int, list] = {}
        for kw in ctx.keywords:
            if kw.status == "ENABLED":
                kws_by_ag.setdefault(kw.ad_group_id, []).append(kw)

        recs: list[Recommendation] = []

        for ag in ctx.ad_groups:
            if ag.impressions < _MIN_IMPRESSIONS:
                continue

            ads = ads_by_ag.get(ag.ad_group_id, [])
            keywords = kws_by_ag.get(ag.ad_group_id, [])
            if not ads or not keywords:
                continue

            # Top-K keywords by impressions represent the ad group's theme
            top_kws = sorted(keywords, key=lambda k: k.impressions, reverse=True)[:_TOP_K_KEYWORDS]
            kw_tokens: set[str] = set()
            for kw in top_kws:
                kw_tokens |= _tokenise(kw.text)
            if not kw_tokens:
                continue

            # Aggregate all headline tokens across all active RSA ads
            headline_tokens: set[str] = set()
            for ad in ads:
                try:
                    headlines: list[str] = json.loads(ad.headlines_json)
                except (json.JSONDecodeError, TypeError):
                    headlines = []
                for h in headlines:
                    headline_tokens |= _tokenise(h)

            if not headline_tokens:
                continue

            coverage = len(kw_tokens & headline_tokens) / len(kw_tokens)
            if coverage >= _MIN_COVERAGE:
                continue

            top_kw_texts = [kw.text for kw in top_kws[:3]]
            target = {"ad_group_id": ag.ad_group_id, "campaign_id": ag.campaign_id}
            payload = {"ad_group_id": ag.ad_group_id, "campaign_id": ag.campaign_id}
            evidence = {
                "ad_group_name": ag.name,
                "top_keywords": top_kw_texts,
                "keyword_tokens": sorted(kw_tokens),
                "headline_tokens": sorted(headline_tokens),
                "keyword_token_coverage": round(coverage, 3),
                "impressions": ag.impressions,
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
