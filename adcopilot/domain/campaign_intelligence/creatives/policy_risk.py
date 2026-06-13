"""PolicyRisk — disapproval-risk rating for a hook, orderable."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import total_ordering


@total_ordering
class PolicyRisk(Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def rank(self) -> int:
        return _ORDER.index(self)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PolicyRisk):
            return NotImplemented
        return self.rank < other.rank


_ORDER = [PolicyRisk.LOW, PolicyRisk.MEDIUM, PolicyRisk.HIGH]


@dataclass(frozen=True)
class PolicyFinding:
    """The screened policy risk of a hook plus a human-readable reason."""

    risk: PolicyRisk
    reason: str = ""

    @classmethod
    def low(cls) -> PolicyFinding:
        return cls(PolicyRisk.LOW, "")
