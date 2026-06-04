"""Enrich proposal keywords with real Keyword Planner demand.

Pure functions (no I/O) so they are trivially testable. Given the LLM/template
keywords for an ad group plus :class:`KeywordIdea` rows from the planner, this:

* attaches ``avg_monthly_searches`` + ``competition`` to keywords the planner
  knows about,
* drops keywords the planner reports as zero-volume (no real demand),
* keeps keywords the planner returned no data for (unknown ≠ zero),
* re-orders so high-demand keywords come first.

A safety rail prevents emptying an ad group: if enrichment would remove every
keyword, the original list is returned unchanged.
"""

from __future__ import annotations

from adcopilot.application.ports.keyword_planner import KeywordIdea
from adcopilot.infrastructure.llm.campaign_generator import KeywordItem


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def enrich_keywords(
    keywords: list[KeywordItem],
    ideas: list[KeywordIdea],
) -> list[KeywordItem]:
    """Return demand-enriched, demand-sorted keywords for one ad group."""
    if not keywords:
        return keywords
    ideas_by_text = {_norm(i.text): i for i in ideas}

    enriched: list[KeywordItem] = []
    for kw in keywords:
        idea = ideas_by_text.get(_norm(kw.text))
        if idea is None:
            # No planner data for this term — keep as-is (unknown, not zero).
            enriched.append(kw)
            continue
        if idea.avg_monthly_searches <= 0:
            # Planner positively reports no demand — drop it.
            continue
        cpc = (
            idea.high_top_of_page_bid_micros / 1_000_000
            if idea.high_top_of_page_bid_micros > 0
            else kw.estimated_cpc_pln
        )
        enriched.append(
            kw.model_copy(
                update={
                    "avg_monthly_searches": idea.avg_monthly_searches,
                    "competition": idea.competition,
                    "estimated_cpc_pln": round(cpc, 2),
                }
            )
        )

    # Don't let enrichment empty the ad group.
    if not enriched:
        return keywords

    # Known-demand keywords first (descending volume); unknown-demand keep order.
    enriched.sort(
        key=lambda k: (
            k.avg_monthly_searches is None,
            -(k.avg_monthly_searches or 0),
        )
    )
    return enriched
