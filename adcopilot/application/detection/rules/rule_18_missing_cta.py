"""Detection rule: active RSA ads have no call-to-action in their copy.

Ads without a clear CTA have lower CTR and conversion rates. Users need
to be told what action to take — 'Buy Now', 'Get a Free Quote', 'Book
Today', etc.
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

# Common English and Polish CTA verbs / phrases.
# Compiled once at module load; checked case-insensitively against the full
# concatenated ad text so multi-word CTAs ('sign up', 'find out') are caught.
_CTA_PATTERNS = re.compile(
    r"\b("
    r"buy|order|shop|purchase|get|grab|claim|"
    r"book|reserve|schedule|appoint|"
    r"sign[\s\-]?up|register|join|subscribe|"
    r"call|contact|reach|chat|"
    r"learn|discover|explore|find out|"
    r"start|try|test|demo|request|"
    r"download|install|"
    r"save|earn|unlock|access|"
    # Polish CTAs
    r"kup|zam[oó]w|zarezerwuj|zapisz|do[łl][aą]cz|"
    r"zadzwo[nń]|skontaktuj|pobierz|wypróbuj|"
    r"sprawdź|dowiedz|odkryj|za[cs]zp[io]sz"
    r")\b",
    re.IGNORECASE,
)


class MissingCtaRule:
    kind = RecommendationKind.MISSING_CTA
    severity = RecommendationSeverity.MEDIUM

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
                descriptions: list[str] = json.loads(ad.descriptions_json)
            except (json.JSONDecodeError, TypeError):
                continue

            all_text = " ".join(headlines + descriptions)
            if _CTA_PATTERNS.search(all_text):
                continue  # CTA found — no issue

            target = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            payload = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            evidence = {
                "ad_id": ad.ad_id,
                "headline_count": len(headlines),
                "impressions": ad.impressions,
                "sample_headlines": headlines[:3],
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
