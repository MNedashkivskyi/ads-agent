"""Keyword Planner adapter — real search-volume data via KeywordPlanIdeaService.

Implements :class:`KeywordPlannerPort`. Fail-open: any error (auth, quota, no
data) returns ``[]`` so the proposal pipeline degrades to template/LLM keywords.

Geo/language: ideas are scoped to Poland nationally
(``geoTargetConstants/2616``) and Polish (``languageConstants/1045``). The
``location`` argument is accepted for future per-region refinement but currently
resolves to national Poland — per-city geo-target-constant IDs are not yet
mapped in this codebase.
"""

from __future__ import annotations

import structlog

from adcopilot.application.ports.keyword_planner import KeywordIdea
from adcopilot.config import Settings
from adcopilot.domain.exceptions import GoogleAdsRateLimited
from adcopilot.infrastructure.google_ads.client import GoogleAdsClientAdapter
from adcopilot.infrastructure.google_ads.retry import retry_on_rate_limit

logger = structlog.get_logger(__name__)

_POLAND_GEO_TARGET = "geoTargetConstants/2616"
_POLISH_LANGUAGE = "languageConstants/1045"


class GoogleKeywordPlannerAdapter:
    """Implements KeywordPlannerPort against the real Keyword Planner API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    async def keyword_ideas(
        self,
        refresh_token: str,
        customer_id: str,
        *,
        seed_keywords: list[str],
        seed_url: str | None = None,
        location: str | None = None,
        language: str = "pl",
        limit: int = 100,
    ) -> list[KeywordIdea]:
        # Trim/clean seeds — the API rejects empty and caps at 20 seed keywords.
        seeds = [k.strip() for k in seed_keywords if k and k.strip()][:20]
        if not seeds and not seed_url:
            return []

        async def _call() -> list[KeywordIdea]:
            return self._generate_ideas(refresh_token, customer_id, seeds, seed_url, limit)

        try:
            # Retry transient quota errors; fail-open on anything else.
            return await retry_on_rate_limit(_call, label="keyword_ideas")
        except Exception as exc:  # fail-open per port contract
            logger.warning(
                "keyword_ideas failed; returning empty",
                customer_id=customer_id,
                error=str(exc),
            )
            return []

    def _generate_ideas(
        self,
        refresh_token: str,
        customer_id: str,
        seeds: list[str],
        seed_url: str | None,
        limit: int,
    ) -> list[KeywordIdea]:
        try:
            client = self._client._build_client(refresh_token)
            cid = customer_id.replace("-", "")
            service = client.get_service("KeywordPlanIdeaService")
            request = client.get_type("GenerateKeywordIdeasRequest")
            request.customer_id = cid
            request.language = _POLISH_LANGUAGE
            request.geo_target_constants.append(_POLAND_GEO_TARGET)
            request.include_adult_keywords = False
            request.keyword_plan_network = (
                client.enums.KeywordPlanNetworkEnum.GOOGLE_SEARCH
            )

            if seeds and seed_url:
                request.keyword_and_url_seed.url = seed_url
                request.keyword_and_url_seed.keywords.extend(seeds)
            elif seeds:
                request.keyword_seed.keywords.extend(seeds)
            else:
                request.url_seed.url = seed_url

            response = service.generate_keyword_ideas(request=request)

            ideas: list[KeywordIdea] = []
            for row in response:
                metrics = row.keyword_idea_metrics
                competition = (
                    metrics.competition.name
                    if metrics and metrics.competition
                    else "UNKNOWN"
                )
                ideas.append(
                    KeywordIdea(
                        text=row.text,
                        avg_monthly_searches=int(
                            getattr(metrics, "avg_monthly_searches", 0) or 0
                        ),
                        competition=competition,
                        low_top_of_page_bid_micros=int(
                            getattr(metrics, "low_top_of_page_bid_micros", 0) or 0
                        ),
                        high_top_of_page_bid_micros=int(
                            getattr(metrics, "high_top_of_page_bid_micros", 0) or 0
                        ),
                    )
                )
                if len(ideas) >= limit:
                    break
            return ideas
        except Exception as exc:
            # Surface quota errors so the retry helper can back off; everything
            # else propagates to the fail-open boundary in keyword_ideas().
            err = str(exc).lower()
            if "quota" in err or "resource exhausted" in err:
                raise GoogleAdsRateLimited(str(exc)) from exc
            raise
