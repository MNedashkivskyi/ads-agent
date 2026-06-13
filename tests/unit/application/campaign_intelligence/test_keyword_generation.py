"""Phase 1 — generation adapter (retry-once) and the generate use case."""

from __future__ import annotations

import pytest

from adcopilot.application.use_cases.campaign_intelligence.keywords.generate_keyword_candidates import (  # noqa: E501
    GenerateKeywordCandidatesUseCase,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)
from adcopilot.domain.exceptions import LLMError
from adcopilot.infrastructure.adapters.claude_generation_adapter import ClaudeKeywordGenerator
from tests.unit.application.campaign_intelligence._fakes import (
    FakeKeywordGenerator,
    FakeKeywordRepository,
)

_VALID = '[{"phrase": "drenaż limfatyczny", "intent": "INTENT", "reasoning": "x"}, ' \
         '{"phrase": "icoone warszawa", "intent": "BRAND", "reasoning": "y"}]'


class SequenceLLM:
    """Returns canned completions in order; records call count."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def complete(self, system: str, user: str, max_tokens: int = 400, temperature: float = 0.3) -> str:
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


# ---------------------------------------------------------------------------
# Adapter — JSON parse + retry-once policy
# ---------------------------------------------------------------------------


async def test_adapter_parses_valid_json_with_fences() -> None:
    llm = SequenceLLM([f"```json\n{_VALID}\n```"])
    gen = ClaudeKeywordGenerator(llm)
    out = await gen.generate(
        service="s", vertical="salon", problems=[], intent_allocation={"INTENT": 1}, language="pl"
    )
    phrases = {g.phrase for g in out}
    assert "drenaż limfatyczny" in phrases
    assert llm.calls == 1


async def test_adapter_retries_once_on_malformed_then_succeeds() -> None:
    llm = SequenceLLM(["not json at all", _VALID])
    gen = ClaudeKeywordGenerator(llm)
    out = await gen.generate(
        service="s", vertical="salon", problems=[], intent_allocation={"INTENT": 2}, language="pl"
    )
    assert out
    assert llm.calls == 2  # exactly one retry


async def test_adapter_raises_after_retry_exhausted() -> None:
    llm = SequenceLLM(["garbage", "still garbage"])
    gen = ClaudeKeywordGenerator(llm)
    with pytest.raises(LLMError):
        await gen.generate(
            service="s", vertical="salon", problems=[], intent_allocation={"INTENT": 1}, language="pl"
        )
    assert llm.calls == 2  # initial + one retry, no more


async def test_adapter_filters_invalid_intents_and_dedups() -> None:
    raw = (
        '[{"phrase":"a","intent":"INTENT"},{"phrase":"a","intent":"INTENT"},'
        '{"phrase":"b","intent":"NONSENSE"},{"phrase":"c","intent":"PROBLEM"}]'
    )
    gen = ClaudeKeywordGenerator(SequenceLLM([raw]))
    out = await gen.generate(
        service="s", vertical="salon", problems=[], intent_allocation={"INTENT": 5}, language="pl"
    )
    phrases = [g.phrase for g in out]
    assert phrases.count("a") == 1  # deduped
    assert "b" not in phrases  # invalid intent dropped
    assert "c" in phrases


# ---------------------------------------------------------------------------
# Use case — slot allocation respected, persisted as generated
# ---------------------------------------------------------------------------


async def test_generate_use_case_covers_all_intents() -> None:
    repo = FakeKeywordRepository()
    run = KeywordRun(
        campaign_id="c1", account_id="a1", user_id="u1", vertical="salon", service="icoone"
    )
    await repo.create_run(run)

    generator = FakeKeywordGenerator()
    use_case = GenerateKeywordCandidatesUseCase(generator, repo)
    await use_case.run(run, total_slots=30)

    assert run.status is KeywordRunStatus.GENERATED
    candidates = await repo.list_candidates(run.id)
    intents = {c.intent.value for c in candidates}
    assert intents == {"BRAND", "INTENT", "PROBLEM"}  # every requested intent present
    # Allocation was uniform (cold start) and summed to total_slots.
    allocation = generator.calls[0]["allocation"]
    assert sum(allocation.values()) == 30
    assert all(v >= 1 for v in allocation.values())


async def test_generate_use_case_feeds_seeds_into_problems() -> None:
    repo = FakeKeywordRepository()
    run = KeywordRun(
        campaign_id="c1",
        account_id="a1",
        user_id="u1",
        vertical="salon",
        service="icoone",
        problems=["cellulit"],
        seeds=["drenaż limfatyczny"],
    )
    await repo.create_run(run)
    generator = FakeKeywordGenerator()
    await GenerateKeywordCandidatesUseCase(generator, repo).run(run)
    problems_seen = generator.calls[0]["problems"]
    assert any("drenaż limfatyczny" in p for p in problems_seen)
    assert "cellulit" in problems_seen
