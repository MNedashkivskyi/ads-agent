"""Unit tests for keyword enrichment (Keyword Planner integration)."""

from __future__ import annotations

import pytest

from adcopilot.application.ports.keyword_planner import KeywordIdea
from adcopilot.application.services.keyword_enrichment import enrich_keywords
from adcopilot.infrastructure.google_ads.fake_keyword_planner import FakeKeywordPlanner
from adcopilot.infrastructure.llm.campaign_generator import KeywordItem


def _idea(text: str, vol: int, comp: str = "MEDIUM", high_bid: int = 2_000_000) -> KeywordIdea:
    return KeywordIdea(
        text=text,
        avg_monthly_searches=vol,
        competition=comp,
        low_top_of_page_bid_micros=500_000,
        high_top_of_page_bid_micros=high_bid,
    )


def test_enrich_attaches_volume_and_sorts_desc():
    kws = [KeywordItem(text="manicure hybrydowy"), KeywordItem(text="paznokcie")]
    ideas = [_idea("paznokcie", 5000), _idea("manicure hybrydowy", 800)]

    out = enrich_keywords(kws, ideas)

    assert [k.text for k in out] == ["paznokcie", "manicure hybrydowy"]
    assert out[0].avg_monthly_searches == 5000
    assert out[0].competition == "MEDIUM"


def test_enrich_drops_zero_volume_keywords():
    kws = [KeywordItem(text="ma demand"), KeywordItem(text="brak demandu")]
    ideas = [_idea("ma demand", 1200), _idea("brak demandu", 0)]

    out = enrich_keywords(kws, ideas)

    assert [k.text for k in out] == ["ma demand"]


def test_enrich_keeps_keywords_without_planner_data():
    # Planner returned nothing for "niszowe" — unknown ≠ zero, so keep it.
    kws = [KeywordItem(text="popularne"), KeywordItem(text="niszowe")]
    ideas = [_idea("popularne", 900)]

    out = enrich_keywords(kws, ideas)

    texts = {k.text for k in out}
    assert texts == {"popularne", "niszowe"}
    # Known-demand first.
    assert out[0].text == "popularne"


def test_enrich_never_empties_ad_group():
    # All keywords report zero volume → would empty the group → keep originals.
    kws = [KeywordItem(text="a"), KeywordItem(text="b")]
    ideas = [_idea("a", 0), _idea("b", 0)]

    out = enrich_keywords(kws, ideas)

    assert len(out) == 2


def test_enrich_is_case_insensitive():
    kws = [KeywordItem(text="Manicure Hybrydowy")]
    ideas = [_idea("manicure hybrydowy", 800)]

    out = enrich_keywords(kws, ideas)

    assert out[0].avg_monthly_searches == 800


def test_enrich_updates_cpc_from_high_bid():
    kws = [KeywordItem(text="x", estimated_cpc_pln=1.0)]
    ideas = [_idea("x", 500, high_bid=3_500_000)]

    out = enrich_keywords(kws, ideas)

    assert out[0].estimated_cpc_pln == 3.5


@pytest.mark.asyncio
async def test_fake_planner_synthesizes_descending_volume():
    planner = FakeKeywordPlanner()
    ideas = await planner.keyword_ideas(
        "rt", "123", seed_keywords=["first", "second", "third"]
    )
    assert [i.avg_monthly_searches for i in ideas] == [1000, 900, 800]
    assert planner.calls[0]["seed_keywords"] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_fake_planner_returns_canned_ideas_when_provided():
    canned = [_idea("z", 42)]
    planner = FakeKeywordPlanner(ideas=canned)
    ideas = await planner.keyword_ideas("rt", "123", seed_keywords=["anything"])
    assert ideas == canned


# --------------------------------------------------------------------------- #
# Pipeline hook: GenerateCampaignProposalUseCase._maybe_enrich_keywords
# --------------------------------------------------------------------------- #


class _AdGroup:
    def __init__(self, keywords):
        self.keywords = keywords


class _Structure:
    def __init__(self, ad_groups):
        self.ad_groups = ad_groups


class _Brief:
    id = "brief-1"
    location = "Warszawa"


def _make_uc(**kwargs):
    from adcopilot.application.use_cases.launch.generate_proposal import (
        GenerateCampaignProposalUseCase,
    )

    return GenerateCampaignProposalUseCase(
        brief_repo=None,
        proposal_repo=None,
        generator=None,
        **kwargs,
    )


@pytest.mark.asyncio
async def test_hook_noop_without_planner():
    uc = _make_uc()  # no planner / creds
    struct = _Structure([_AdGroup([KeywordItem(text="a"), KeywordItem(text="b")])])
    await uc._maybe_enrich_keywords(struct, _Brief())
    # Unchanged.
    assert [k.text for k in struct.ad_groups[0].keywords] == ["a", "b"]
    assert struct.ad_groups[0].keywords[0].avg_monthly_searches is None


@pytest.mark.asyncio
async def test_hook_enriches_when_planner_and_creds_present():
    ideas = [_idea("b", 5000), _idea("a", 100)]
    planner = FakeKeywordPlanner(ideas=ideas)
    uc = _make_uc(
        keyword_planner=planner,
        account_refresh_token="rt",
        account_customer_id="123",
    )
    struct = _Structure([_AdGroup([KeywordItem(text="a"), KeywordItem(text="b")])])

    await uc._maybe_enrich_keywords(struct, _Brief())

    kws = struct.ad_groups[0].keywords
    assert [k.text for k in kws] == ["b", "a"]  # sorted by demand
    assert kws[0].avg_monthly_searches == 5000
    # Planner was called with the seeds + location.
    assert planner.calls[0]["location"] == "Warszawa"


@pytest.mark.asyncio
async def test_hook_failopen_on_planner_error():
    class _BoomPlanner:
        async def keyword_ideas(self, *a, **k):
            raise RuntimeError("api down")

    uc = _make_uc(
        keyword_planner=_BoomPlanner(),
        account_refresh_token="rt",
        account_customer_id="123",
    )
    struct = _Structure([_AdGroup([KeywordItem(text="a")])])
    # Must not raise.
    await uc._maybe_enrich_keywords(struct, _Brief())
    assert [k.text for k in struct.ad_groups[0].keywords] == ["a"]
