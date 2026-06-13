"""HookGeneratorPort + HookJudgePort — the creative track's LLM interfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GeneratedHook:
    """One LLM-generated hook, tagged by angle and the surface it targets."""

    text: str
    angle: str
    surface: str


@dataclass(frozen=True)
class JudgeResult:
    """Per-criterion judge scores for one hook (each 0..1) plus the overall."""

    text: str
    specificity: float
    tension: float
    pain_truth: float
    clarity: float

    @property
    def overall(self) -> float:
        return (self.specificity + self.tension + self.pain_truth + self.clarity) / 4.0


class HookGeneratorPort(Protocol):
    async def generate(
        self,
        *,
        service: str,
        vertical: str,
        problems: list[str],
        angle_allocation: dict[str, int],
        surfaces: list[str],
        language: str = "pl",
        focus: str | None = None,
    ) -> list[GeneratedHook]:
        """Return hooks spanning the requested angles and surfaces, within limits.

        ``focus`` optionally steers generation toward one ad group's theme.
        """
        ...


class HookJudgePort(Protocol):
    async def judge(
        self,
        hooks: list[GeneratedHook],
        *,
        service: str,
        vertical: str,
        language: str = "pl",
    ) -> list[JudgeResult]:
        """Score each hook on specificity/tension/pain-truth/clarity (0..1)."""
        ...
