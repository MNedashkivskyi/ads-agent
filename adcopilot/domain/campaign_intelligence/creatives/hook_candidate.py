"""HookCandidate — one generated hook for a specific surface and angle.

The char limit is enforced at construction: an over-limit headline is a hard
error (Google would reject the asset), so it can never enter the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from adcopilot.domain.campaign_intelligence.creatives.ad_surface import (
    AdSurface,
    char_limit,
    within_limit,
)
from adcopilot.domain.campaign_intelligence.creatives.angle import Angle
from adcopilot.domain.campaign_intelligence.creatives.hook_score import HookScore
from adcopilot.domain.campaign_intelligence.creatives.policy_risk import PolicyFinding


class HookStatus(StrEnum):
    GENERATED = "generated"
    SELECTED = "selected"
    FINALIZED = "finalized"
    REJECTED = "rejected"


@dataclass
class HookCandidate:
    text: str
    angle: Angle
    surface: AdSurface
    policy: PolicyFinding = field(default_factory=PolicyFinding.low)
    score: HookScore | None = None
    judge_score: float | None = None
    status: HookStatus = HookStatus.GENERATED
    pinned_slot: str | None = None
    id: str | None = None

    def __post_init__(self) -> None:
        self.text = self.text.strip()
        if not self.text:
            raise ValueError("Hook text must not be empty")
        if not within_limit(self.surface, self.text):
            raise ValueError(
                f"Hook '{self.text}' ({len(self.text)} chars) exceeds the "
                f"{char_limit(self.surface)}-char limit for {self.surface.value}"
            )

    @property
    def char_count(self) -> int:
        return len(self.text)

    @property
    def final_score(self) -> float:
        return self.score.value if self.score else 0.0
