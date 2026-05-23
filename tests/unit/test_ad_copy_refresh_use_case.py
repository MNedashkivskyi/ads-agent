"""Unit tests for AdCopyRefreshUseCase."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.use_cases.refresh_ad_copy import AdCopyRefreshUseCase, _parse_proposals
from adcopilot.domain.ad_copy_proposal import AdCopyProposal
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


def _make_rec(evidence: dict) -> Recommendation:
    return Recommendation(
        id=RecommendationId("rec-1"),
        account_id=AccountId("acc-1"),
        kind=RecommendationKind.AD_FATIGUE,
        severity=RecommendationSeverity.MEDIUM,
        target={"account_id": "acc-1"},
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=0,
        created_at=datetime.now(UTC),
        status=RecommendationStatus.PENDING,
    )


_SAMPLE_JSON = json.dumps([
    {"headlines": ["Kup Teraz", "Najlepsza Cena", "Sprawdź Ofertę"], "descriptions": ["Szeroki wybór produktów dla Twojej firmy.", "Zamów online i oszczędź czas i pieniądze."]},
    {"headlines": ["Zadzwoń Dziś", "Szybka Dostawa", "Bez Opłat"], "descriptions": ["Doradztwo 7 dni w tygodniu dla Ciebie.", "Bezpłatna wysyłka przy zamówieniu powyżej 200 zł."]},
    {"headlines": ["Dowiedz Się Więcej", "Top Jakość", "Skontaktuj Się"], "descriptions": ["Produkty od sprawdzonych dostawców z UE.", "Zapytaj o rabat dla stałych klientów firmy."]},
])


def test_parse_proposals_returns_three_variants() -> None:
    proposals = _parse_proposals(_SAMPLE_JSON, "https://example.com")
    assert len(proposals) == 3
    for p in proposals:
        assert isinstance(p, AdCopyProposal)
        assert len(p.headlines) == 3
        assert len(p.descriptions) == 2


def test_parse_proposals_enforces_headline_length() -> None:
    raw = json.dumps([
        {"headlines": ["A" * 35, "Short", "Also Fine"], "descriptions": ["Desc one is acceptable length here.", "Desc two is also fine here."]},
        {"headlines": ["H1", "H2", "H3"], "descriptions": ["D1", "D2"]},
        {"headlines": ["H1", "H2", "H3"], "descriptions": ["D1", "D2"]},
    ])
    proposals = _parse_proposals(raw, "https://x.com")
    assert len(proposals[0].headlines[0]) <= 30


def test_parse_proposals_enforces_description_length() -> None:
    long_desc = "X" * 100
    raw = json.dumps([
        {"headlines": ["H1", "H2", "H3"], "descriptions": [long_desc, "Short desc."]},
        {"headlines": ["H1", "H2", "H3"], "descriptions": ["D1", "D2"]},
        {"headlines": ["H1", "H2", "H3"], "descriptions": ["D1", "D2"]},
    ])
    proposals = _parse_proposals(raw, "")
    assert len(proposals[0].descriptions[0]) <= 90


def test_parse_proposals_raises_on_no_json() -> None:
    with pytest.raises(ValueError, match="No JSON array"):
        _parse_proposals("Coś poszło nie tak", "")


@pytest.mark.asyncio
async def test_execute_returns_three_proposals() -> None:
    llm = AsyncMock()
    llm.complete.return_value = _SAMPLE_JSON

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = (
        "Kampania: {campaign_name}, Branża: {vertical}, "
        "Słowa: {keyword_themes}, Nagłówki: {existing_headlines}, Opisy: {existing_descriptions}"
    )
    prompt_repo.get_latest.return_value = pv

    use_case = AdCopyRefreshUseCase(llm=llm, prompt_repo=prompt_repo)
    rec = _make_rec({
        "campaign_name": "Sklep Sportowy",
        "vertical": "sport",
        "keyword_themes": "buty biegowe",
        "headlines": ["Biegnij Szybciej"],
        "descriptions": ["Najlepsze buty na rynku."],
        "final_url": "https://sklep.pl",
    })
    proposals = await use_case.execute(rec)
    assert len(proposals) == 3
    assert proposals[0].final_url == "https://sklep.pl"


@pytest.mark.asyncio
async def test_execute_wraps_missing_prompt_evidence_gracefully() -> None:
    llm = AsyncMock()
    llm.complete.return_value = _SAMPLE_JSON

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = "{campaign_name} {vertical} {keyword_themes} {existing_headlines} {existing_descriptions}"
    prompt_repo.get_latest.return_value = pv

    use_case = AdCopyRefreshUseCase(llm=llm, prompt_repo=prompt_repo)
    rec = _make_rec({})  # empty evidence — defaults kick in
    proposals = await use_case.execute(rec)
    assert len(proposals) == 3
