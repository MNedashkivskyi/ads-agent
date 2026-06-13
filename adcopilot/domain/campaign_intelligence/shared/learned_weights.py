"""learned_weights — turn learned DimensionPerformance into scorer multipliers.

The scorers (keyword intent-weight, hook angle-prior) want a multiplicative
weight centred on 1.0: winners > 1, losers < 1. We derive that from the
smoothed scores, relative to the group mean, and include *only trusted values*
(those past MIN_SAMPLE). Untrusted/cold-start values are omitted, so the scorer
falls back to its static prior for them — graceful cold start, no crash on empty.
"""

from __future__ import annotations

from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    MIN_SAMPLE,
    DimensionPerformance,
)


def weights_from_performance(
    performance: dict[str, DimensionPerformance],
    *,
    min_sample: int = MIN_SAMPLE,
    floor: float = 0.25,
    ceiling: float = 3.0,
) -> dict[str, float]:
    """Return value → multiplicative weight (≈1.0 mean) for trusted values only."""
    trusted = {
        v: p.smoothed_score
        for v, p in performance.items()
        if p.sample_size >= min_sample
    }
    if not trusted:
        return {}
    mean = sum(trusted.values()) / len(trusted)
    if mean <= 0:
        return {}
    return {
        v: max(floor, min(ceiling, score / mean)) for v, score in trusted.items()
    }
