"""KeywordPlannerPort — read keyword ideas with real demand from Google Ads.

Backed by the Keyword Planner (``KeywordPlanIdeaService``). Used by the launch
proposal pipeline to replace blind LLM/template keyword guesses with terms that
have measured search volume, competition and top-of-page bid ranges.

The contract is fail-open: implementations never raise — they return ``[]`` on
any API error — so the proposal pipeline degrades gracefully to its previous
template/LLM behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class KeywordIdea:
    """One keyword idea with demand and bid signals.

    ``competition`` is "LOW" / "MEDIUM" / "HIGH" / "UNKNOWN". Bid bounds are in
    micros of the account currency (1_000_000 micros = 1 unit).
    """

    text: str
    avg_monthly_searches: int
    competition: str
    low_top_of_page_bid_micros: int
    high_top_of_page_bid_micros: int


class KeywordPlannerPort(Protocol):
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
        """Return keyword ideas seeded by keywords and/or a URL.

        Never raises — returns ``[]`` on any error (auth, quota, no data).
        """
        ...
