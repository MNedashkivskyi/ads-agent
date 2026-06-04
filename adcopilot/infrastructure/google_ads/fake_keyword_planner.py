"""Fake KeywordPlannerPort for unit tests."""

from __future__ import annotations

from adcopilot.application.ports.keyword_planner import KeywordIdea


class FakeKeywordPlanner:
    """Returns canned keyword ideas without hitting the Google Ads API.

    Pass ``ideas`` to control the returned list, or leave it ``None`` to derive
    deterministic ideas from the seed keywords (descending volume). Records each
    call in ``self.calls``.
    """

    def __init__(self, ideas: list[KeywordIdea] | None = None) -> None:
        self._ideas = ideas
        self.calls: list[dict[str, object]] = []

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
        self.calls.append(
            {
                "customer_id": customer_id,
                "seed_keywords": list(seed_keywords),
                "seed_url": seed_url,
                "location": location,
                "language": language,
            }
        )
        if self._ideas is not None:
            return self._ideas[:limit]
        # Deterministic synthetic ideas: descending volume by seed order.
        out: list[KeywordIdea] = []
        for i, seed in enumerate(seed_keywords):
            out.append(
                KeywordIdea(
                    text=seed,
                    avg_monthly_searches=max(0, 1000 - i * 100),
                    competition="MEDIUM",
                    low_top_of_page_bid_micros=500_000,
                    high_top_of_page_bid_micros=2_000_000,
                )
            )
        return out[:limit]
