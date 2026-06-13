"""Bayesian smoothing — shrink a value's rate toward the vertical prior.

A dimension value with only a handful of impressions cannot be trusted: a single
fluky conversion gives it a 100% rate. We correct this with a shrinkage estimator
(additive smoothing toward a prior): the observed rate is blended with the
vertical-wide prior, weighted by how much data the value has. With little data
the estimate sits near the prior; with lots of data it converges on the observed
rate. This is what stops "a 3-impression value out-ranking a 50,000-impression
value" — the 3-impression rate is pulled almost entirely back to the prior.

Pure functions, no I/O. Used by ``recompute_dimension_weights`` (shared) for both
keyword-intent and creative-angle learning.
"""

from __future__ import annotations

# Strength of the prior, in pseudo-observations. Roughly: how many real
# observations a value needs before its own rate counts for half the estimate.
DEFAULT_PRIOR_STRENGTH = 30.0

# How much CTR contributes to the combined score relative to conversion rate.
# Conversions are the ground truth that matters most, so they dominate; CTR is a
# secondary signal that breaks ties when conversion data is still sparse.
CTR_WEIGHT = 0.2


def smooth_rate(
    observed_rate: float,
    sample_size: float,
    prior_rate: float,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
) -> float:
    """Shrink *observed_rate* toward *prior_rate*, weighted by *sample_size*.

    ``smoothed = (observed * n + prior * k) / (n + k)`` where ``n`` is the
    sample size and ``k`` is the prior strength. With ``n == 0`` the result is
    exactly the prior; as ``n → ∞`` it converges on the observed rate.
    """
    n = max(sample_size, 0.0)
    denom = n + prior_strength
    if denom <= 0:
        return observed_rate
    return (observed_rate * n + prior_rate * prior_strength) / denom


def combined_score(smoothed_ctr: float, smoothed_conv: float) -> float:
    """Combine smoothed CTR and conversion rate into one allocation score.

    Conversion rate dominates; CTR is down-weighted to a tie-breaker so that a
    high-CTR / zero-conversion value cannot out-rank one that actually converts.
    """
    return max(smoothed_conv, 0.0) + CTR_WEIGHT * max(smoothed_ctr, 0.0)


def smoothed_metrics(
    *,
    impressions: float,
    clicks: float,
    conversions: float,
    prior_ctr: float,
    prior_conv: float,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
) -> tuple[float, float, float]:
    """Return ``(weighted_ctr, weighted_conv, smoothed_score)`` for one value.

    ``weighted_ctr`` and ``weighted_conv`` are the *observed* rates (clicks per
    impression, conversions per click). ``smoothed_score`` is the shrinkage
    estimate used for ranking/allocation: CTR is smoothed against impressions,
    conversion rate against clicks, then combined.
    """
    ctr = (clicks / impressions) if impressions > 0 else 0.0
    conv = (conversions / clicks) if clicks > 0 else 0.0
    s_ctr = smooth_rate(ctr, impressions, prior_ctr, prior_strength)
    s_conv = smooth_rate(conv, clicks, prior_conv, prior_strength)
    return ctr, conv, combined_score(s_ctr, s_conv)
