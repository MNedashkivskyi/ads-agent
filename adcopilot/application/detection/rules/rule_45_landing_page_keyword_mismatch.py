"""Rule 45 — Landing Page Keyword Mismatch.

Fires when the top-performing keywords in an ad group have low lexical overlap
(< 30 %) with the ad's landing page content (title + H1 + body text sample).

Low overlap is a Quality Score signal: Google's ad relevance metric penalises
campaigns where keywords don't appear on the destination page.  This rule
detects the mismatch so a human can update copy or create a dedicated landing
page.

This is a NON_EXECUTABLE rule — it surfaces an advisory card only.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime

from adcopilot.application.detection.base import DetectionContext, LandingPageData
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)

_MIN_OVERLAP = 0.30
_TOP_KEYWORDS = 5
_MIN_IMPRESSIONS = 100  # only consider keywords with meaningful traffic


def _tokenize(text: str) -> set[str]:
    """Lower-case word tokens > 2 chars (supports Polish diacritics)."""
    return {w for w in re.findall(r"[a-zA-ZąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", text.lower()) if len(w) > 2}


class LandingPageKeywordMismatchRule:
    kind = RecommendationKind.LANDING_PAGE_KEYWORD_MISMATCH
    severity = RecommendationSeverity.MEDIUM

    def detect(self, ctx: DetectionContext) -> list[Recommendation]:
        if not ctx.landing_page_results:
            return []

        # Index keywords by ad_group_id, sorted by impressions desc
        kw_by_ag: dict[int, list[str]] = {}
        for kw in sorted(ctx.keywords, key=lambda k: -k.impressions):
            if kw.impressions < _MIN_IMPRESSIONS:
                continue
            kw_by_ag.setdefault(kw.ad_group_id, [])
            if len(kw_by_ag[kw.ad_group_id]) < _TOP_KEYWORDS:
                kw_by_ag[kw.ad_group_id].append(kw.text)

        recs: list[Recommendation] = []

        for ad in ctx.ads:
            if ad.status != "ENABLED":
                continue
            try:
                urls: list[str] = json.loads(ad.final_urls_json or "[]")
            except Exception:
                continue
            if not urls:
                continue

            url = urls[0]
            lp: LandingPageData | None = ctx.landing_page_results.get(url)
            if lp is None or not lp.reachable:
                continue

            kws = kw_by_ag.get(ad.ad_group_id, [])
            if not kws:
                continue

            kw_tokens = _tokenize(" ".join(kws))
            if not kw_tokens:
                continue

            page_content = " ".join(filter(None, [lp.page_title, lp.h1_text, lp.body_text_sample]))
            if not page_content:
                continue

            page_tokens = _tokenize(page_content)
            overlap = kw_tokens & page_tokens
            ratio = len(overlap) / len(kw_tokens)

            if ratio >= _MIN_OVERLAP:
                continue

            missing = sorted(kw_tokens - page_tokens)[:5]

            # Enrich evidence with GA4 bounce rate when available
            from urllib.parse import urlparse

            page_path = urlparse(url).path or "/"
            ga4 = ctx.ga4_page_metrics.get(page_path)
            ga4_evidence: dict = {}
            if ga4:
                ga4_evidence = {
                    "ga4_sessions": ga4.sessions,
                    "ga4_bounce_rate": ga4.bounce_rate,
                    "ga4_avg_session_duration_sec": ga4.avg_session_duration_sec,
                    "ga4_pages_per_session": ga4.pages_per_session,
                }

            recs.append(
                Recommendation(
                    id=RecommendationId(str(uuid.uuid4())),
                    account_id=ctx.account.id,  # type: ignore[arg-type]
                    kind=self.kind,
                    severity=self.severity,
                    target={"ad_id": ad.ad_id, "url": url},
                    payload={
                        "ad_id": ad.ad_id,
                        "ad_group_id": ad.ad_group_id,
                        "url": url,
                        "overlap_ratio": round(ratio, 3),
                        "missing_tokens": missing,
                        "top_keywords": kws,
                        **ga4_evidence,
                    },
                    evidence={
                        "overlap_ratio": round(ratio, 3),
                        "missing_tokens": missing,
                        "top_keywords": kws,
                        **ga4_evidence,
                    },
                    estimated_monthly_savings_micros=0,
                    created_at=datetime.now(tz=UTC),
                    status=RecommendationStatus.PENDING,
                )
            )

        return recs
