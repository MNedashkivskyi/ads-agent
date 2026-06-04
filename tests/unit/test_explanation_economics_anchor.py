"""BC3: recommendation explanations are anchored to the client's economics."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adcopilot.domain.business_economics import BusinessEconomics
from adcopilot.domain.recommendation import (
    Recommendation,
    RecommendationKind,
    RecommendationSeverity,
    RecommendationStatus,
)


class FakeLLM:
    def __init__(self):
        self.last_user = None

    async def complete(self, *, system, user, max_tokens=400, temperature=0.3):
        self.last_user = user
        return "wyjaśnienie"


class FakeRepo:
    def __init__(self, rec):
        self._rec = rec
        self.explanation = None

    async def get(self, rec_id):
        return self._rec

    async def update_explanation(self, rec_id, explanation):
        self.explanation = explanation


def _rec() -> Recommendation:
    return Recommendation(
        id="r1",
        account_id="a1",
        kind=RecommendationKind.PAUSE_KEYWORD,
        severity=RecommendationSeverity.MEDIUM,
        target={"criterion_id": 1},
        payload={},
        estimated_monthly_savings_micros=0,
        evidence={"keyword_text": "buty"},
        created_at=datetime.now(UTC),
        status=RecommendationStatus.PENDING,
    )


async def _explain(business_context):
    from adcopilot.application.use_cases.explain_recommendation import ExplainRecommendationUseCase

    llm = FakeLLM()
    uc = ExplainRecommendationUseCase(llm=llm, repo=FakeRepo(_rec()))
    await uc.execute("r1", language="pl", business_context=business_context)
    return llm.last_user


@pytest.mark.asyncio
async def test_prompt_includes_economics_when_configured() -> None:
    econ = BusinessEconomics(account_id="a1", primary_goal="LEADS", target_cpa=80.0, target_roas=4.0)
    prompt = await _explain(econ)
    assert "Kontekst biznesowy" in prompt
    assert "docelowy CPA=80" in prompt
    assert "LEADS" in prompt


@pytest.mark.asyncio
async def test_prompt_omits_economics_when_unconfigured() -> None:
    assert "Kontekst biznesowy" not in (await _explain(None))
    # Value-only economics (no goal/targets) does not count as context.
    econ = BusinessEconomics(account_id="a1", default_lead_value=150.0)
    assert "Kontekst biznesowy" not in (await _explain(econ))
