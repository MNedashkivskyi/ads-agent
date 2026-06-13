"""Phase 2 — expansion: flag gating, dedupe, and the DataForSEO cost ceiling."""

from __future__ import annotations

import httpx
import pytest
import respx

from adcopilot.application.ports.keyword_generator import GeneratedKeyword
from adcopilot.application.ports.keyword_volume import VolumeRequestContext
from adcopilot.application.use_cases.campaign_intelligence.keywords.expand_keywords import (
    ExpandKeywordsUseCase,
)
from adcopilot.config import Settings
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import KeywordCandidate
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import KeywordRun
from adcopilot.domain.campaign_intelligence.keywords.value_objects import KeywordIntent
from adcopilot.infrastructure.adapters.dataforseo_adapter import DataForSeoAdapter
from tests.unit.application.campaign_intelligence._fakes import FakeKeywordRepository


class FakeExpander:
    is_configured = True

    def __init__(self, results: list[GeneratedKeyword]) -> None:
        self._results = results
        self.calls = 0
        self.seeds_seen: list[str] = []

    async def expand_keywords(self, seeds, ctx, *, limit=100, max_requests=None):  # noqa: ANN001
        self.calls += 1
        self.seeds_seen = seeds
        return self._results


async def _seed_run(repo: FakeKeywordRepository, phrases: list[str]) -> KeywordRun:
    run = KeywordRun(campaign_id="c1", account_id="a1", user_id="u1", vertical="salon")
    await repo.create_run(run)
    await repo.replace_candidates(
        run.id,
        run.campaign_id,
        [KeywordCandidate(phrase=p, intent=KeywordIntent.INTENT) for p in phrases],
    )
    return run


async def test_disabled_flag_makes_no_call() -> None:
    repo = FakeKeywordRepository()
    run = await _seed_run(repo, ["drenaż limfatyczny"])
    expander = FakeExpander([GeneratedKeyword("x", "INTENT")])
    uc = ExpandKeywordsUseCase(expander, repo, enabled=False, max_requests=3)
    added = await uc.run(run)
    assert added == []
    assert expander.calls == 0


async def test_expansion_dedupes_against_existing() -> None:
    repo = FakeKeywordRepository()
    run = await _seed_run(repo, ["drenaż limfatyczny"])
    expander = FakeExpander(
        [
            GeneratedKeyword("drenaż limfatyczny", "INTENT"),  # already present
            GeneratedKeyword("masaż wyszczuplający", "INTENT"),  # new
        ]
    )
    uc = ExpandKeywordsUseCase(expander, repo, enabled=True, max_requests=3)
    added = await uc.run(run)
    assert [c.phrase for c in added] == ["masaż wyszczuplający"]
    assert all(c.source == "expansion" for c in added)
    # Seeds came from the run's INTENT candidates.
    assert "drenaż limfatyczny" in expander.seeds_seen


@respx.mock
async def test_dataforseo_expansion_respects_cost_ceiling() -> None:
    settings = Settings(DATAFORSEO_LOGIN="u", DATAFORSEO_PASSWORD="p")
    adapter = DataForSeoAdapter(settings)
    route = respx.post(
        "https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"tasks": [{"result": [{"keyword": "x"}]}]},
        )
    )
    seeds = ["s1", "s2", "s3", "s4", "s5"]
    await adapter.expand_keywords(seeds, VolumeRequestContext(), max_requests=2)
    # Halts at the configured budget — never exceeds 2 requests despite 5 seeds.
    assert adapter.request_count == 2
    assert route.call_count == 2


@respx.mock
async def test_dataforseo_search_volume_returns_exact_numbers() -> None:
    settings = Settings(DATAFORSEO_LOGIN="u", DATAFORSEO_PASSWORD="p")
    adapter = DataForSeoAdapter(settings)
    respx.post(
        "https://api.dataforseo.com/v3/keywords_data/google_ads/search_volume/live"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "result": [
                            {"keyword": "drenaż limfatyczny", "search_volume": 8100,
                             "competition": "MEDIUM"},
                        ]
                    }
                ]
            },
        )
    )
    out = await adapter.fetch_volumes(["drenaż limfatyczny"], VolumeRequestContext())
    sv = out["drenaż limfatyczny"]
    assert sv.monthly_searches == 8100
    assert sv.is_bucketed is False
