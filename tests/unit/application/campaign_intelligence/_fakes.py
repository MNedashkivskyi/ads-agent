"""In-memory fakes for CIE ports — let the keyword/creative flows run without a DB."""

from __future__ import annotations

import uuid

from adcopilot.application.ports.keyword_generator import GeneratedKeyword
from adcopilot.application.ports.keyword_volume import VolumeRequestContext
from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import (
    KeywordCandidate,
    KeywordStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)
from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KeywordScore,
    SearchVolume,
)


class FakeRedis:
    """Minimal RedisLike for KeywordVolumeCache tests."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value


class FakeKeywordGenerator:
    """Returns candidates respecting the requested intent allocation."""

    def __init__(self, by_intent: dict[str, list[str]] | None = None) -> None:
        self._by_intent = by_intent
        self.calls: list[dict] = []

    async def generate(
        self,
        *,
        service: str,
        vertical: str,
        problems: list[str],
        intent_allocation: dict[str, int],
        language: str = "pl",
    ) -> list[GeneratedKeyword]:
        self.calls.append(
            {
                "service": service,
                "vertical": vertical,
                "problems": problems,
                "allocation": dict(intent_allocation),
                "language": language,
            }
        )
        out: list[GeneratedKeyword] = []
        for intent, count in intent_allocation.items():
            phrases = (self._by_intent or {}).get(intent)
            if phrases is None:
                phrases = [f"{intent.lower()}-kw-{i}" for i in range(count)]
            for phrase in phrases[:count]:
                out.append(GeneratedKeyword(phrase=phrase, intent=intent, reasoning="test"))
        return out


class FakeVolumePort:
    """Configurable volume backend that records which phrases it was asked about."""

    def __init__(self, volumes: dict[str, SearchVolume], name: str = "fake") -> None:
        self._volumes = {k.strip().lower(): v for k, v in volumes.items()}
        self.name = name
        self.requested: list[str] = []
        self.call_count = 0

    async def fetch_volumes(
        self, phrases: list[str], ctx: VolumeRequestContext
    ) -> dict[str, SearchVolume]:
        self.call_count += 1
        self.requested.extend(p.strip().lower() for p in phrases)
        return {
            p.strip().lower(): self._volumes[p.strip().lower()]
            for p in phrases
            if p.strip().lower() in self._volumes
        }


class FakeKeywordRepository:
    """In-memory CieKeywordRepository."""

    def __init__(self) -> None:
        self.runs: dict[str, KeywordRun] = {}
        self.candidates: dict[str, list[KeywordCandidate]] = {}

    async def create_run(self, run: KeywordRun) -> str:
        run.id = run.id or str(uuid.uuid4())
        self.runs[run.id] = run
        self.candidates.setdefault(run.id, [])
        return run.id

    async def get_run(self, run_id: str) -> KeywordRun | None:
        return self.runs.get(run_id)

    async def get_latest_run_for_campaign(
        self, campaign_id: str, user_id: str
    ) -> KeywordRun | None:
        matches = [
            r
            for r in self.runs.values()
            if r.campaign_id == campaign_id and r.user_id == user_id
        ]
        return matches[-1] if matches else None

    async def set_run_status(
        self, run_id: str, status: KeywordRunStatus, error: str | None = None
    ) -> None:
        run = self.runs.get(run_id)
        if run:
            run.status = status
            if error:
                run.error = error

    async def replace_candidates(
        self, run_id: str, campaign_id: str, candidates: list[KeywordCandidate]
    ) -> None:
        for i, c in enumerate(candidates):
            c.id = c.id or f"{run_id}:{i}"
        self.candidates[run_id] = list(candidates)

    async def add_candidates(
        self, run_id: str, campaign_id: str, candidates: list[KeywordCandidate]
    ) -> None:
        existing = {c.phrase.strip().lower() for c in self.candidates.get(run_id, [])}
        for i, c in enumerate(candidates):
            if c.phrase.strip().lower() in existing:
                continue
            c.id = c.id or f"{run_id}:add:{i}"
            self.candidates.setdefault(run_id, []).append(c)

    async def list_candidates(
        self, run_id: str, *, statuses: list[str] | None = None
    ) -> list[KeywordCandidate]:
        items = self.candidates.get(run_id, [])
        if statuses:
            items = [c for c in items if c.status.value in statuses]
        return list(items)

    async def save_candidate(self, candidate: KeywordCandidate) -> None:
        for run_candidates in self.candidates.values():
            for i, c in enumerate(run_candidates):
                if c.id == candidate.id:
                    run_candidates[i] = candidate
                    return


def make_volume(searches: int, *, bucketed: bool = False, competition: str = "MEDIUM") -> SearchVolume:
    return SearchVolume(
        monthly_searches=searches,
        competition=competition,
        cpc_low_micros=500_000,
        cpc_high_micros=2_000_000,
        is_bucketed=bucketed,
    )


def make_score(value: float) -> KeywordScore:
    return KeywordScore(value)
