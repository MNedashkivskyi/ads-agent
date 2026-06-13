"""PerformanceLabel — Google Ads asset performance rating, made orderable.

Google Ads rates each ad asset (headline, description, ...) with a performance
label once it has enough data: ``PENDING`` → ``LEARNING`` → ``LOW`` / ``GOOD`` /
``BEST``. We parse from the Google Ads string form (including ``UNKNOWN`` /
``UNSPECIFIED`` / empty, which map to ``PENDING``) and make labels orderable so
"a BEST asset outranks a GOOD asset" is a plain comparison.
"""

from __future__ import annotations

from enum import Enum
from functools import total_ordering


@total_ordering
class PerformanceLabel(Enum):
    """An asset's learned performance rating. Orderable: BEST > GOOD > LOW >
    LEARNING > PENDING."""

    PENDING = "PENDING"
    LEARNING = "LEARNING"
    LOW = "LOW"
    GOOD = "GOOD"
    BEST = "BEST"

    @property
    def rank(self) -> int:
        """Monotonic rank for ordering (PENDING=0 .. BEST=4)."""
        return _ORDER.index(self)

    @classmethod
    def parse(cls, raw: str | None) -> PerformanceLabel:
        """Parse from the Google Ads enum string.

        ``UNKNOWN`` / ``UNSPECIFIED`` / ``None`` / empty all map to PENDING — the
        asset simply hasn't been rated yet.
        """
        if not raw:
            return cls.PENDING
        key = raw.strip().upper()
        try:
            return cls(key)
        except ValueError:
            return cls.PENDING

    @property
    def is_rated(self) -> bool:
        """True once Google has assigned a real rating (LOW/GOOD/BEST)."""
        return self in (PerformanceLabel.LOW, PerformanceLabel.GOOD, PerformanceLabel.BEST)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, PerformanceLabel):
            return NotImplemented
        return self.rank < other.rank


_ORDER: list[PerformanceLabel] = [
    PerformanceLabel.PENDING,
    PerformanceLabel.LEARNING,
    PerformanceLabel.LOW,
    PerformanceLabel.GOOD,
    PerformanceLabel.BEST,
]
