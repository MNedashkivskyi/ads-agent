"""CieKeywordRepository — persistence port for keyword runs + candidates."""

from __future__ import annotations

from typing import Protocol

from adcopilot.domain.campaign_intelligence.keywords.keyword_candidate import KeywordCandidate
from adcopilot.domain.campaign_intelligence.keywords.keyword_run import (
    KeywordRun,
    KeywordRunStatus,
)


class CieKeywordRepository(Protocol):
    async def create_run(self, run: KeywordRun) -> str:
        """Persist a new run; return its id."""
        ...

    async def get_run(self, run_id: str) -> KeywordRun | None: ...

    async def get_latest_run_for_campaign(
        self, campaign_id: str, user_id: str
    ) -> KeywordRun | None: ...

    async def set_run_status(
        self, run_id: str, status: KeywordRunStatus, error: str | None = None
    ) -> None: ...

    async def replace_candidates(
        self, run_id: str, campaign_id: str, candidates: list[KeywordCandidate]
    ) -> None:
        """Replace all candidates for a run (used on (re)generation)."""
        ...

    async def add_candidates(
        self, run_id: str, campaign_id: str, candidates: list[KeywordCandidate]
    ) -> None:
        """Append candidates (used by harvest seed-back / expansion)."""
        ...

    async def list_candidates(
        self, run_id: str, *, statuses: list[str] | None = None
    ) -> list[KeywordCandidate]: ...

    async def save_candidate(self, candidate: KeywordCandidate) -> None:
        """Persist updates to a single candidate (volume, score, status)."""
        ...

    async def list_phrases_for_campaign(self, campaign_id: str) -> set[str]:
        """All phrases already present for a campaign (for dedupe)."""
        ...
