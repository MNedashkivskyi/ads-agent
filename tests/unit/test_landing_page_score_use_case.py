"""Unit tests for LandingPageScoreUseCase."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.use_cases.score_landing_page import (
    LandingPageScoreUseCase,
    _parse_recommendations,
)
from adcopilot.domain.landing_page_score import CoreWebVitals, LandingPageScore


def _make_score(performance: int = 72) -> LandingPageScore:
    return LandingPageScore(
        url="https://example.com",
        performance_score=performance,
        accessibility_score=85,
        seo_score=90,
        best_practices_score=78,
        mobile_friendly=True,
        core_web_vitals=CoreWebVitals(
            lcp_ms=2500.0, fcp_ms=1100.0, cls_score=0.08, tbt_ms=200.0, ttfb_ms=180.0
        ),
        recommendations_pl=[],
        scored_at=datetime.now(UTC),
    )


def test_parse_recommendations_valid_json() -> None:
    raw = json.dumps(["Zoptymalizuj obrazy", "Dodaj metatytuł", "Popraw kontrast kolorów"])
    recs = _parse_recommendations(raw)
    assert len(recs) == 3
    assert recs[0] == "Zoptymalizuj obrazy"


def test_parse_recommendations_extracts_from_prose() -> None:
    raw = 'Oto rekomendacje: ["Zoptymalizuj obrazy", "Dodaj metatytuł", "Popraw kontrast"]'
    recs = _parse_recommendations(raw)
    assert len(recs) == 3


def test_parse_recommendations_empty_on_invalid() -> None:
    recs = _parse_recommendations("Coś poszło nie tak")
    assert recs == []


def test_parse_recommendations_truncates_to_3() -> None:
    raw = json.dumps(["R1", "R2", "R3", "R4", "R5"])
    recs = _parse_recommendations(raw)
    assert len(recs) == 3


@pytest.mark.asyncio
async def test_execute_returns_score_with_recommendations() -> None:
    page_analyzer = AsyncMock()
    page_analyzer.analyze.return_value = _make_score(72)

    llm = AsyncMock()
    llm.complete.return_value = json.dumps(
        ["Zoptymalizuj obrazy PNG", "Wdróż lazy loading", "Skompresuj CSS"]
    )

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = (
        "URL: {url}, perf: {performance_score}, acc: {accessibility_score}, "
        "seo: {seo_score}, bp: {best_practices_score}, mobile: {mobile_friendly}, "
        "lcp: {lcp_ms}, fcp: {fcp_ms}, cls: {cls_score}, tbt: {tbt_ms}, ttfb: {ttfb_ms}"
    )
    prompt_repo.get_latest.return_value = pv

    use_case = LandingPageScoreUseCase(
        page_analyzer=page_analyzer, llm=llm, prompt_repo=prompt_repo
    )
    result = await use_case.execute("https://example.com")

    assert result.performance_score == 72
    assert len(result.recommendations_pl) == 3
    assert "Zoptymalizuj" in result.recommendations_pl[0]


@pytest.mark.asyncio
async def test_execute_handles_bad_llm_response_gracefully() -> None:
    page_analyzer = AsyncMock()
    page_analyzer.analyze.return_value = _make_score()

    llm = AsyncMock()
    llm.complete.return_value = "Przepraszam, nie mogę wygenerować rekomendacji."

    prompt_repo = AsyncMock()
    pv = MagicMock()
    pv.content = "{url} {performance_score} {accessibility_score} {seo_score} {best_practices_score} {mobile_friendly} {lcp_ms} {fcp_ms} {cls_score} {tbt_ms} {ttfb_ms}"
    prompt_repo.get_latest.return_value = pv

    use_case = LandingPageScoreUseCase(
        page_analyzer=page_analyzer, llm=llm, prompt_repo=prompt_repo
    )
    result = await use_case.execute("https://example.com")

    assert result.recommendations_pl == []  # graceful degradation
