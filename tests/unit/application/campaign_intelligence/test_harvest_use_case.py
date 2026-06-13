"""Phase 5.2/5.4 — harvest use case: read facts → proposals, idempotent."""

from __future__ import annotations

from datetime import date

from adcopilot.application.ports.cie_performance import PerformanceFact
from adcopilot.application.use_cases.campaign_intelligence.keywords.harvest_search_terms import (
    HarvestSearchTermsUseCase,
)
from tests.unit.application.campaign_intelligence._fakes import (
    FakeAttributionRepository,
    FakeFactRepository,
    FakeSearchTermRepository,
)

_ACCOUNT = "11111111-1111-1111-1111-111111111111"
_DAY = date(2026, 6, 10)


def _st_fact(term: str, *, clicks: int, conversions: float, cost: int) -> PerformanceFact:
    return PerformanceFact(
        account_id=_ACCOUNT, customer_id="123", entity_type="search_term",
        entity_id=f"st_{term}", day=_DAY, dimension="keyword_intent", value="INTENT",
        vertical="salon", language="pl", impressions=1000, clicks=clicks,
        conversions=conversions, cost_micros=cost,
        extra={"search_term": term, "matched_keyword": "drenaż limfatyczny"},
    )


async def _run(facts: FakeFactRepository, proposals: FakeSearchTermRepository) -> None:
    attribution = FakeAttributionRepository(intent_map={"drenaż limfatyczny": "INTENT"})
    await HarvestSearchTermsUseCase(facts, attribution, proposals).run(
        account_id=_ACCOUNT, customer_id="123", vertical="salon", language="pl"
    )


async def test_harvest_produces_promotions_and_negatives() -> None:
    facts = FakeFactRepository()
    await facts.upsert_facts(
        [
            _st_fact("masaż wyszczuplający", clicks=40, conversions=5.0, cost=10_000_000),
            _st_fact("praca w spa", clicks=50, conversions=0.0, cost=30_000_000),
            # Already a keyword — must not be re-proposed.
            _st_fact("drenaż limfatyczny", clicks=80, conversions=9.0, cost=20_000_000),
        ]
    )
    proposals = FakeSearchTermRepository()
    await _run(facts, proposals)

    promotions = [s for s in proposals.saved if s["kind"] == "promote"]
    negatives = [s for s in proposals.saved if s["kind"] == "negative"]
    terms = {s["term"] for s in proposals.saved}
    assert "masaż wyszczuplający" in {s["term"] for s in promotions}
    assert "praca w spa" in {s["term"] for s in negatives}
    assert "drenaż limfatyczny" not in terms  # existing keyword excluded


async def test_harvest_is_idempotent() -> None:
    facts = FakeFactRepository()
    await facts.upsert_facts(
        [_st_fact("masaż wyszczuplający", clicks=40, conversions=5.0, cost=10_000_000)]
    )
    proposals = FakeSearchTermRepository()
    await _run(facts, proposals)
    await _run(facts, proposals)
    assert len(proposals.saved) == 1  # no duplicate proposals


async def test_promotion_terms_available_as_seeds() -> None:
    facts = FakeFactRepository()
    await facts.upsert_facts(
        [_st_fact("masaż wyszczuplający", clicks=40, conversions=5.0, cost=10_000_000)]
    )
    proposals = FakeSearchTermRepository()
    await _run(facts, proposals)
    seeds = await proposals.list_promotion_terms(_ACCOUNT)
    assert "masaż wyszczuplający" in seeds  # feeds back into next generation
