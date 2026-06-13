"""DimensionPerformance — learned metrics for one (vertical, dimension, value).

The single unit of learned knowledge in the spine. One row per
``(vertical, dimension, value, language)`` says: across every campaign in this
vertical, how did this dimension value perform? ``sample_size`` (impressions) is
the trust signal — it gates whether the learned ``smoothed_score`` is believed or
the value is still treated as cold-start (see ``MIN_SAMPLE``).

The same entity holds "PROBLEM keywords convert best in beauty" and
"failed-alternative hooks convert best in beauty" — ``dimension`` distinguishes
them. Pure data + a builder; no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from adcopilot.domain.campaign_intelligence.shared import bayesian_smoothing

# Minimum impressions before a value's learned weight is trusted. Below this the
# selector/scorer treat the value as cold-start (neutral, explore). Conservative
# by default; tune from the Phase 6 backtest.
MIN_SAMPLE = 1000


@dataclass(frozen=True)
class DimensionPerformance:
    """Aggregated, smoothed performance for one dimension value in a vertical."""

    vertical: str
    dimension: str
    value: str
    sample_size: int  # impressions — the trust signal
    clicks: int
    conversions: float
    weighted_ctr: float  # observed clicks / impressions
    weighted_conv: float  # observed conversions / clicks
    smoothed_score: float  # Bayesian-smoothed combined score (for ranking)
    language: str = "pl"
    extra: dict = field(default_factory=dict)

    @property
    def is_trusted(self) -> bool:
        """True once the value has enough impressions to trust its weight."""
        return self.sample_size >= MIN_SAMPLE

    @classmethod
    def from_aggregates(
        cls,
        *,
        vertical: str,
        dimension: str,
        value: str,
        impressions: int,
        clicks: int,
        conversions: float,
        prior_ctr: float,
        prior_conv: float,
        language: str = "pl",
        prior_strength: float = bayesian_smoothing.DEFAULT_PRIOR_STRENGTH,
    ) -> DimensionPerformance:
        """Build from raw counts plus the vertical priors, smoothing on the fly."""
        weighted_ctr, weighted_conv, score = bayesian_smoothing.smoothed_metrics(
            impressions=impressions,
            clicks=clicks,
            conversions=conversions,
            prior_ctr=prior_ctr,
            prior_conv=prior_conv,
            prior_strength=prior_strength,
        )
        return cls(
            vertical=vertical,
            dimension=dimension,
            value=value,
            sample_size=impressions,
            clicks=clicks,
            conversions=conversions,
            weighted_ctr=weighted_ctr,
            weighted_conv=weighted_conv,
            smoothed_score=score,
            language=language,
        )
