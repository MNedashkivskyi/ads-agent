"""KeywordCandidate — a generated keyword moving through its lifecycle.

generated → (validate volumes) → validated | rejected. Carries its intent-type
tag (the strategic dimension) from birth so that, once shipped, performance can
be attributed back to the dimension value. The volume and score are populated
during validation/ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from adcopilot.domain.campaign_intelligence.keywords.value_objects import (
    KeywordIntent,
    KeywordScore,
    SearchVolume,
)


class KeywordStatus(StrEnum):
    GENERATED = "generated"
    VALIDATED = "validated"
    REJECTED = "rejected"


@dataclass
class KeywordCandidate:
    """A keyword candidate. Mutable — status advances through the pipeline."""

    phrase: str
    intent: KeywordIntent
    volume: SearchVolume | None = None
    score: KeywordScore | None = None
    status: KeywordStatus = KeywordStatus.GENERATED
    source: str = "llm"  # llm | expansion | harvest
    reasoning: str = ""
    id: str | None = None
    extra: dict = field(default_factory=dict)

    def mark_validated(self, volume: SearchVolume) -> None:
        """Attach validated volume and mark validated, or reject if non-viable."""
        self.volume = volume
        if volume.is_viable:
            self.status = KeywordStatus.VALIDATED
        else:
            self.status = KeywordStatus.REJECTED

    def mark_rejected(self) -> None:
        self.status = KeywordStatus.REJECTED

    def with_score(self, score: KeywordScore) -> None:
        self.score = score

    @property
    def is_validated(self) -> bool:
        return self.status is KeywordStatus.VALIDATED
