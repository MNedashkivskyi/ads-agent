"""dimension_selector — explore/exploit slot allocation across a dimension.

Given ``total_slots`` candidate slots and the learned performance of each value
on a dimension, decide how many slots each value gets in the next generation
round. Written once, used by both tracks: the keyword track allocates slots
across BRAND/INTENT/PROBLEM; the creative track allocates across its angles.

Design goals (all unit-tested):

* **Cold start → uniform.** With no trustworthy data, every value gets an equal
  share. New verticals work immediately and get smarter on their own.
* **Exploit winners.** Once values cross ``MIN_SAMPLE``, higher smoothed scores
  earn proportionally more slots.
* **Never let anything die.** A per-value floor (≥ 1) plus an exploration bonus
  keeps every value in play, so the loop can't collapse onto a single value and
  a temporarily-losing value still gets a chance to recover.

Pure functions, no I/O.
"""

from __future__ import annotations

from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    MIN_SAMPLE,
    DimensionPerformance,
)

# Fraction of the mean weight added to every value as an exploration bonus. Keeps
# losing values from being starved below their proportional-plus-floor share, so
# the allocation never collapses onto one value.
DEFAULT_EXPLORE_FRACTION = 0.20


def allocate(
    total_slots: int,
    values: list[str],
    performance: dict[str, DimensionPerformance],
    *,
    floor: int = 1,
    min_sample: int = MIN_SAMPLE,
    explore_fraction: float = DEFAULT_EXPLORE_FRACTION,
) -> dict[str, int]:
    """Allocate *total_slots* across *values* using learned *performance*.

    ``performance`` maps a value → its :class:`DimensionPerformance` (may omit
    values that have no data yet). Returns a value → slot-count map that sums to
    ``total_slots`` and gives every value at least ``floor`` slots.

    Raises ``ValueError`` if there aren't enough slots to honour the floor for
    every value (callers must request ``total_slots >= len(values) * floor``).
    """
    if not values:
        return {}
    n = len(values)
    if floor < 0:
        raise ValueError("floor must be >= 0")
    if total_slots < n * floor:
        raise ValueError(
            f"total_slots={total_slots} cannot honour floor={floor} for {n} values"
        )

    # Trusted weights: only values past MIN_SAMPLE contribute a learned score.
    trusted: dict[str, float] = {
        v: max(perf.smoothed_score, 0.0)
        for v in values
        if (perf := performance.get(v)) is not None and perf.sample_size >= min_sample
    }

    floored = {v: floor for v in values}
    remaining = total_slots - n * floor
    if remaining <= 0:
        return floored

    # Cold start (or every trusted weight is zero): distribute the remainder
    # uniformly via the proportional path with equal weights.
    if not trusted or all(w <= 0 for w in trusted.values()):
        weights = {v: 1.0 for v in values}
    else:
        # Untrusted values get the neutral (mean) trusted weight so they are
        # neither punished nor rewarded for lacking data — they just explore.
        mean_trusted = sum(trusted.values()) / len(trusted)
        base = {v: trusted.get(v, mean_trusted) for v in values}
        # Exploration bonus relative to the mean keeps every value in contention.
        bonus = explore_fraction * (sum(base.values()) / n)
        weights = {v: base[v] + bonus for v in values}

    extra = _largest_remainder(remaining, weights, values)
    return {v: floored[v] + extra[v] for v in values}


def _largest_remainder(
    total: int, weights: dict[str, float], order: list[str]
) -> dict[str, int]:
    """Apportion *total* integer slots proportional to *weights* deterministically.

    Uses the largest-remainder (Hamilton) method: floor each ideal share, then
    hand out the leftover slots to the values with the largest fractional
    remainders. Ties broken by *order* so the result is fully deterministic.
    """
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        # Degenerate — spread as evenly as possible in declared order.
        result = {v: total // len(order) for v in order}
        for v in order[: total % len(order)]:
            result[v] += 1
        return result

    ideal = {v: total * weights[v] / weight_sum for v in order}
    base = {v: int(ideal[v]) for v in order}
    handed_out = sum(base.values())
    leftover = total - handed_out
    # Order by fractional remainder desc, then declared order for stable ties.
    ranked = sorted(
        order,
        key=lambda v: (-(ideal[v] - base[v]), order.index(v)),
    )
    for v in ranked[:leftover]:
        base[v] += 1
    return base
