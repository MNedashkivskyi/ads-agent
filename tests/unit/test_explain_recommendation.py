"""Tests for ExplainRecommendationUseCase and prompt templates."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from adcopilot.application.detection.templates import format_micros_as_currency
from adcopilot.application.use_cases.explain_recommendation import ExplainRecommendationUseCase
from adcopilot.domain.entities import AccountId
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationId,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)
from adcopilot.infrastructure.llm.fake_client import FakeLLMClient

_ACCOUNT_ID = AccountId("acct-1")
_NOW = datetime(2026, 4, 10, tzinfo=UTC)


def _rec(
    kind: RecommendationKind,
    evidence: dict,
    savings_micros: int = 5_000_000,
) -> Recommendation:
    return Recommendation(
        id=RecommendationId(str(uuid.uuid4())),
        account_id=_ACCOUNT_ID,
        kind=kind,
        severity=RecommendationSeverity.HIGH,
        target={"ad_group_id": 1},
        payload={},
        evidence=evidence,
        estimated_monthly_savings_micros=savings_micros,
        created_at=_NOW,
        status=RecommendationStatus.PENDING,
    )


def _repo(rec: Recommendation) -> MagicMock:
    repo = MagicMock()
    repo.get = AsyncMock(return_value=rec)
    repo.update_explanation = AsyncMock()
    return repo


# ---------------------------------------------------------------------------
# format_micros_as_currency
# ---------------------------------------------------------------------------


def test_format_micros_eur() -> None:
    assert format_micros_as_currency(10_500_000) == "€10.50"


def test_format_micros_usd() -> None:
    assert format_micros_as_currency(1_000_000, "USD") == "$1.00"


def test_format_micros_pln() -> None:
    # Polish convention: no decimals for whole amounts, comma for grosze,
    # non-breaking-space thousands separator.
    assert format_micros_as_currency(50_000_000, "PLN") == "50 zł"
    assert format_micros_as_currency(50_500_000, "PLN") == "50,50 zł"


def test_format_micros_zero() -> None:
    assert format_micros_as_currency(0) == "€0.00"


# ---------------------------------------------------------------------------
# ExplainRecommendationUseCase — golden tests with FakeLLMClient
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_explain_add_negative_keyword_mentions_search_term() -> None:
    """LLM user prompt for ADD_NEGATIVE_KEYWORD must contain the search term."""
    llm = FakeLLMClient(default="Twoja reklama wyświetliła się na frazę 'free shoes'.")
    rec = _rec(
        RecommendationKind.ADD_NEGATIVE_KEYWORD,
        evidence={"search_term": "free shoes", "clicks": 10, "cost_micros": 3_000_000},
    )
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    explanation = await uc.execute(rec.id)

    assert "free shoes" in explanation
    assert len(llm.calls) == 1
    assert "free shoes" in llm.calls[0]["user"]


@pytest.mark.asyncio
async def test_explain_pause_keyword_mentions_keyword_text() -> None:
    """LLM user prompt for PAUSE_KEYWORD must contain the keyword text."""
    llm = FakeLLMClient(default="Keyword 'running shoes' should be paused.")
    rec = _rec(
        RecommendationKind.PAUSE_KEYWORD,
        evidence={"keyword_text": "running shoes", "clicks": 35, "cost_micros": 25_000_000},
    )
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    explanation = await uc.execute(rec.id, language="en")

    assert "running shoes" in explanation
    assert "running shoes" in llm.calls[0]["user"]


@pytest.mark.asyncio
async def test_explain_conversion_tracking_prompt_mentions_tracking() -> None:
    """Prompt for ENABLE_CONVERSION_TRACKING should contain cost mention."""
    llm = FakeLLMClient(default="You have no conversion tracking configured. This is critical.")
    rec = _rec(
        RecommendationKind.ENABLE_CONVERSION_TRACKING,
        evidence={"total_cost_micros": 200_000_000, "total_conversions": 0},
        savings_micros=0,
    )
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    explanation = await uc.execute(rec.id, language="en")

    assert "tracking" in explanation.lower() or "konwersj" in explanation.lower()


@pytest.mark.asyncio
async def test_explain_calls_update_explanation_with_llm_output() -> None:
    """update_explanation must be called with the exact LLM response."""
    expected = "This is the LLM explanation."
    llm = FakeLLMClient(default=expected)
    rec = _rec(RecommendationKind.PAUSE_KEYWORD, evidence={"keyword_text": "test"})
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    result = await uc.execute(rec.id)

    assert result == expected
    repo.update_explanation.assert_awaited_once_with(rec.id, expected)


@pytest.mark.asyncio
async def test_explain_missing_evidence_keys_do_not_crash() -> None:
    """Empty evidence dict should not raise KeyError."""
    llm = FakeLLMClient(default="fallback explanation")
    rec = _rec(RecommendationKind.ADD_NEGATIVE_KEYWORD, evidence={})
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    # Should not raise
    result = await uc.execute(rec.id)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_explain_raises_if_recommendation_not_found() -> None:
    """ValueError raised when recommendation_id not found."""
    llm = FakeLLMClient()
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    with pytest.raises(ValueError, match="not found"):
        await uc.execute(RecommendationId(str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_explain_uses_system_prompt() -> None:
    """The SYSTEM_PROMPT must be passed to the LLM client."""
    from adcopilot.application.detection.templates import SYSTEM_PROMPT

    llm = FakeLLMClient(default="ok")
    rec = _rec(RecommendationKind.PAUSE_KEYWORD, evidence={"keyword_text": "x"})
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    await uc.execute(rec.id)

    assert llm.calls[0]["system"] == SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_explain_polish_language_uses_pl_template() -> None:
    """Polish language ('pl') selects the PL template."""
    llm = FakeLLMClient(default="Po polsku: zatrzymaj to słowo.")
    rec = _rec(
        RecommendationKind.PAUSE_KEYWORD,
        evidence={"keyword_text": "buty", "clicks": 5, "cost_micros": 1_000_000},
    )
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    await uc.execute(rec.id, language="pl")

    user_prompt = llm.calls[0]["user"]
    assert "polsku" in user_prompt or "Słowo" in user_prompt


@pytest.mark.asyncio
async def test_explain_savings_formatted_in_prompt() -> None:
    """Estimated savings must appear in the user prompt in EUR format."""
    llm = FakeLLMClient(default="You can save money.")
    rec = _rec(
        RecommendationKind.ADD_NEGATIVE_KEYWORD,
        evidence={"search_term": "example", "clicks": 6, "cost_micros": 4_000_000},
        savings_micros=4_000_000,
    )
    repo = _repo(rec)
    uc = ExplainRecommendationUseCase(llm=llm, repo=repo)

    await uc.execute(rec.id, language="en")

    # €4.00 should appear in the user prompt
    assert "€4.00" in llm.calls[0]["user"]
