"""Detection rule: RSA ad descriptions contain no concrete specifics —
no numbers, prices, percentages, or measurable claims.

Generic copy like "High quality service" or "Best solutions for your
business" performs worse than specific copy ("Save 30%", "From €49/month",
"1,000+ happy clients") because specifics build trust and stand out in a
sea of similar-sounding ads.

A description scores a 'specificity point' for each of the following it
contains: a number, a currency symbol, a percentage, or a recognised
specificity anchor word.  Descriptions with zero specificity points across
ALL descriptions trigger the rule.
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
_MIN_IMPRESSIONS = 200

# Patterns that signal specific, concrete copy
_HAS_NUMBER = re.compile(r"\d")  # any digit
_HAS_CURRENCY = re.compile(r"[$€£₽zł]")  # currency symbols
_HAS_PERCENT = re.compile(r"\d+\s*%")  # e.g. "30%"
_HAS_ANCHOR = re.compile(
    r"\b("
    r"free|guarantee|guaranteed|warranty|"
    r"award|certified|accredited|licensed|"
    r"same[\s\-]day|next[\s\-]day|24[\s/]7|"
    r"no[\s\-]contract|no[\s\-]commitment|"
    r"money[\s\-]back|refund|"
    # Polish
    r"bezp[łl]atnie|gwarancja|certyfikowany|"
    r"tego samego dnia|bez umowy|zwrot pieni[eę]dzy"
    r")\b",
    re.IGNORECASE,
)


def _is_specific(text: str) -> bool:
    return bool(
        _HAS_NUMBER.search(text)
        or _HAS_CURRENCY.search(text)
        or _HAS_PERCENT.search(text)
        or _HAS_ANCHOR.search(text)
    )


class GenericDescriptionRule:
    kind = RecommendationKind.GENERIC_DESCRIPTION
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
                descriptions: list[str] = json.loads(ad.descriptions_json)
            except (json.JSONDecodeError, TypeError):
                continue

            if not descriptions:
                continue

            # All descriptions must be generic for the rule to fire
            if any(_is_specific(d) for d in descriptions):
                continue

            target = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            payload = {"ad_id": ad.ad_id, "ad_group_id": ad.ad_group_id}
            evidence = {
                "ad_id": ad.ad_id,
                "descriptions": descriptions[:3],
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
