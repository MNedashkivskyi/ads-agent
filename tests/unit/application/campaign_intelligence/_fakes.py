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

    async def list_phrases_for_campaign(self, campaign_id: str) -> set[str]:
        phrases: set[str] = set()
        for run in self.runs.values():
            if run.campaign_id != campaign_id or run.id is None:
                continue
            phrases.update(c.phrase.strip().lower() for c in self.candidates.get(run.id, []))
        return phrases


class FakeHookGenerator:
    """Generates one HEADLINE + one DESCRIPTION per allocated angle."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def generate(
        self,
        *,
        service: str,
        vertical: str,
        problems: list[str],
        angle_allocation: dict[str, int],
        surfaces: list[str],
        language: str = "pl",
    ):  # noqa: ANN201
        from adcopilot.application.ports.hook_generator import GeneratedHook

        self.calls.append({"allocation": dict(angle_allocation), "surfaces": list(surfaces)})
        out: list[GeneratedHook] = []
        for angle in angle_allocation:
            if "HEADLINE" in surfaces:
                out.append(GeneratedHook(f"{angle[:10].title()} hook?", angle, "HEADLINE"))
            if "DESCRIPTION" in surfaces:
                out.append(
                    GeneratedHook(f"{angle.title()} opis który konwertuje dobrze", angle, "DESCRIPTION")
                )
        return out


class FakeHookJudge:
    """Scores hooks; a chosen ``winner_angle`` gets the top marks."""

    def __init__(self, winner_angle: str = "PAIN") -> None:
        self._winner = winner_angle
        self.calls = 0

    async def judge(self, hooks, *, service, vertical, language="pl"):  # noqa: ANN001
        from adcopilot.application.ports.hook_generator import JudgeResult

        self.calls += 1
        out = []
        for h in hooks:
            base = 0.9 if h.angle == self._winner else 0.5
            out.append(
                JudgeResult(
                    text=h.text,
                    specificity=base,
                    tension=base,
                    pain_truth=base,
                    clarity=base,
                )
            )
        return out


class FakeHookRepository:
    """In-memory CieHookRepository."""

    def __init__(self) -> None:
        self.runs: dict = {}
        self.candidates: dict = {}
        self.shipped_assets: list = []

    async def create_run(self, run) -> str:  # noqa: ANN001
        run.id = run.id or str(uuid.uuid4())
        self.runs[run.id] = run
        self.candidates.setdefault(run.id, [])
        return run.id

    async def get_run(self, run_id):  # noqa: ANN001
        return self.runs.get(run_id)

    async def get_latest_run_for_campaign(self, campaign_id, user_id):  # noqa: ANN001
        matches = [
            r for r in self.runs.values()
            if r.campaign_id == campaign_id and r.user_id == user_id
        ]
        return matches[-1] if matches else None

    async def set_run_status(self, run_id, status, error=None):  # noqa: ANN001
        run = self.runs.get(run_id)
        if run:
            run.status = status
            if error:
                run.error = error

    async def set_rsa_payload(self, run_id, payload):  # noqa: ANN001
        run = self.runs.get(run_id)
        if run:
            run.rsa_payload = payload

    async def replace_candidates(self, run_id, campaign_id, candidates):  # noqa: ANN001
        for i, c in enumerate(candidates):
            c.id = c.id or f"{run_id}:{i}"
        self.candidates[run_id] = list(candidates)

    async def list_candidates(self, run_id, *, statuses=None):  # noqa: ANN001
        items = self.candidates.get(run_id, [])
        if statuses:
            items = [c for c in items if c.status.value in statuses]
        return list(items)

    async def save_candidate(self, candidate):  # noqa: ANN001
        for run_candidates in self.candidates.values():
            for i, c in enumerate(run_candidates):
                if c.id == candidate.id:
                    run_candidates[i] = candidate
                    return

    async def record_shipped_assets(self, *, account_id, customer_id, campaign_id,
                                    vertical, language, assets):  # noqa: ANN001
        for c in assets:
            key = (account_id, c.text, c.surface.value)
            if any((a["account_id"], a["asset_text"], a["surface"]) == key for a in self.shipped_assets):
                continue
            self.shipped_assets.append(
                {
                    "account_id": account_id,
                    "customer_id": customer_id,
                    "campaign_id": campaign_id,
                    "asset_text": c.text,
                    "angle": c.angle.value,
                    "surface": c.surface.value,
                    "vertical": vertical,
                    "language": language,
                }
            )


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
