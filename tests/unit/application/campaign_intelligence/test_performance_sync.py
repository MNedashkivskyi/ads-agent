"""Phase 4 — performance ingest: dimension attribution + idempotency."""

from __future__ import annotations

from datetime import date

from adcopilot.application.ports.ads_performance import (
    AssetPerformanceRow,
    KeywordPerformanceRow,
    SearchTermRow,
)
from adcopilot.application.use_cases.campaign_intelligence.shared.sync_ads_performance import (
    SyncAdsPerformanceUseCase,
)
from tests.unit.application.campaign_intelligence._fakes import (
    FakeAttributionRepository,
    FakeFactRepository,
    FakePerformancePort,
)

_DAY = date(2026, 6, 10)
_ACCOUNT = "11111111-1111-1111-1111-111111111111"


def _assets() -> list[AssetPerformanceRow]:
    return [
        AssetPerformanceRow(
            account_id="", customer_id="123", day=_DAY, asset_id="A1",
            asset_text="Cellulit, który nie znika?", field_type="HEADLINE",
            ad_group_id="ag1", campaign_id="c1", impressions=1000, clicks=80,
            conversions=8.0, cost_micros=50_000_000, performance_label="BEST",
        ),
    ]


def _keywords() -> list[KeywordPerformanceRow]:
    return [
        KeywordPerformanceRow(
            account_id="", customer_id="123", day=_DAY, criterion_id="K1",
            keyword_text="drenaż limfatyczny", match_type="PHRASE", ad_group_id="ag1",
            campaign_id="c1", impressions=2000, clicks=120, conversions=12.0,
            cost_micros=60_000_000,
        ),
    ]


def _search_terms() -> list[SearchTermRow]:
    return [
        SearchTermRow(
            account_id="", customer_id="123", day=_DAY,
            search_term="masaż wyszczuplający brzucha", matched_keyword_text="drenaż limfatyczny",
            ad_group_id="ag1", campaign_id="c1", impressions=300, clicks=30,
            conversions=4.0, cost_micros=10_000_000, status="NONE",
        ),
    ]


def _use_case(facts: FakeFactRepository) -> SyncAdsPerformanceUseCase:
    attribution = FakeAttributionRepository(
        intent_map={"drenaż limfatyczny": "INTENT"},
        angle_map={"cellulit, który nie znika?": "PAIN"},
    )
    port = FakePerformancePort(
        assets=_assets(), keywords=_keywords(), search_terms=_search_terms()
    )
    return SyncAdsPerformanceUseCase(port, attribution, facts)


async def test_sync_attributes_both_tracks() -> None:
    facts = FakeFactRepository()
    result = await _use_case(facts).run(
        account_id=_ACCOUNT, customer_id="123", refresh_token="tok",
        vertical="salon", language="pl", start_date=_DAY, end_date=_DAY,
    )
    assert result.assets == 1 and result.keywords == 1 and result.search_terms == 1

    asset_fact = facts.facts[(_ACCOUNT, "asset", "A1", _DAY)]
    assert asset_fact.dimension == "angle"
    assert asset_fact.value == "PAIN"  # asset attributed to its angle
    assert asset_fact.performance_label == "BEST"

    kw_fact = facts.facts[(_ACCOUNT, "keyword", "K1", _DAY)]
    assert kw_fact.dimension == "keyword_intent"
    assert kw_fact.value == "INTENT"  # keyword attributed to its intent

    # The search term is stored with its matched-keyword intent for harvesting.
    st_facts = await facts.list_search_term_facts(_ACCOUNT)
    assert len(st_facts) == 1
    assert st_facts[0].extra["search_term"] == "masaż wyszczuplający brzucha"
    assert st_facts[0].value == "INTENT"


async def test_sync_is_idempotent_on_double_run() -> None:
    facts = FakeFactRepository()
    await _use_case(facts).run(
        account_id=_ACCOUNT, customer_id="123", refresh_token="tok",
        vertical="salon", language="pl", start_date=_DAY, end_date=_DAY,
    )
    first = dict(facts.facts)
    # Re-run the same day — no new rows, keyed by (entity, day).
    await _use_case(facts).run(
        account_id=_ACCOUNT, customer_id="123", refresh_token="tok",
        vertical="salon", language="pl", start_date=_DAY, end_date=_DAY,
    )
    assert set(facts.facts.keys()) == set(first.keys())
    assert len(facts.facts) == 3  # asset + keyword + search_term, no duplicates


async def test_unattributed_entity_still_stored() -> None:
    facts = FakeFactRepository()
    # No attribution maps → values are None but facts are still recorded.
    port = FakePerformancePort(assets=_assets(), keywords=_keywords())
    use_case = SyncAdsPerformanceUseCase(port, FakeAttributionRepository(), facts)
    await use_case.run(
        account_id=_ACCOUNT, customer_id="123", refresh_token="tok",
        vertical="salon", language="pl", start_date=_DAY, end_date=_DAY,
    )
    assert facts.facts[(_ACCOUNT, "asset", "A1", _DAY)].value is None
    assert facts.facts[(_ACCOUNT, "keyword", "K1", _DAY)].value is None
