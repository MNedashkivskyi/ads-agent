"""Seasonal adjustment for week-over-week detection thresholds.

Several trend rules (CPA spike, CVR drop, spend acceleration, CTR decline,
impression-share erosion) compare this week to last week against a fixed
threshold. During a vertical's high-demand month those metrics swing for
structural reasons (more lower-intent traffic, higher competition, naturally
rising spend), which fires false alerts. This widens the threshold in peak
months so only genuinely abnormal swings trigger.

Design choice — **relax in peak, never tighten in trough**: in low-demand months
conversion volume is small and metrics are noisy, so tightening there would
*increase* false positives. We therefore only ever raise the bar (peak), never
lower it below the rule's base threshold.

Seasonality is keyed off ``ctx.snapshot_date.month`` (deterministic + testable),
not the wall clock.
"""

from __future__ import annotations

from adcopilot.application.detection.base import DetectionContext
from adcopilot.domain.polish_market.seasonality import get_seasonal_multiplier


def seasonal_multiplier(ctx: DetectionContext) -> float:
    """Demand multiplier for the context's vertical in the snapshot month.

    Returns 1.0 when the vertical is unknown or has no seasonal profile, so rules
    behave exactly as before for unclassified accounts.
    """
    vertical = ctx.vertical
    if not vertical:
        return 1.0
    try:
        return get_seasonal_multiplier(vertical, ctx.snapshot_date.month)
    except Exception:
        return 1.0


def seasonal_relaxed_threshold(base: float, multiplier: float) -> float:
    """Widen a deviation threshold during peak months; never below ``base``.

    ``base * max(1.0, multiplier)`` — peak (multiplier > 1) requires a larger
    week-over-week deviation before firing; trough (multiplier < 1) leaves the
    threshold at ``base``.
    """
    return base * max(1.0, multiplier)
