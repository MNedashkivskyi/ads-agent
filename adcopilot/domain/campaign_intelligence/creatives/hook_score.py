"""HookScore — a hook's combined score and its components."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HookScore:
    value: float
    judge: float = 0.0
    heuristic: float = 0.0
    angle_prior: float = 1.0

    @classmethod
    def zero(cls) -> HookScore:
        return cls(0.0)
