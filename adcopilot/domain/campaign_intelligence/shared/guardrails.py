"""guardrails — health checks on learned weights (pure).

Two failure modes to alert on (Phase 7.5):

* **drift** — a dimension value's smoothed score moved more than ``drift_threshold``
  (relative) since the last recompute. Sudden swings usually mean a data or
  attribution bug, not a real shift in customer behaviour.
* **starved** — a value has some data but is stuck below ``MIN_SAMPLE``, so it
  never graduates to learned weighting. Persistent starvation means the vertical
  isn't accumulating enough volume to learn.

Pure; returns alert descriptors for a notifier/logger to deliver.
"""

from __future__ import annotations

from dataclasses import dataclass

from adcopilot.domain.campaign_intelligence.shared.dimension_performance import (
    MIN_SAMPLE,
    DimensionPerformance,
)

DRIFT = "drift"
STARVED = "starved"
DEFAULT_DRIFT_THRESHOLD = 0.5


@dataclass(frozen=True)
class GuardrailAlert:
    kind: str
    dimension: str
    vertical: str
    value: str
    detail: str


def _key(p: DimensionPerformance) -> str:
    return f"{p.vertical}:{p.dimension}:{p.value}:{p.language}"


def check_guardrails(
    performances: list[DimensionPerformance],
    previous_scores: dict[str, float] | None = None,
    *,
    drift_threshold: float = DEFAULT_DRIFT_THRESHOLD,
    min_sample: int = MIN_SAMPLE,
) -> list[GuardrailAlert]:
    """Return guardrail alerts for drift and starved sample sizes."""
    previous_scores = previous_scores or {}
    alerts: list[GuardrailAlert] = []

    for p in performances:
        # Starved: has data but never crosses the trust threshold.
        if 0 < p.sample_size < min_sample:
            alerts.append(
                GuardrailAlert(
                    kind=STARVED,
                    dimension=p.dimension,
                    vertical=p.vertical,
                    value=p.value,
                    detail=f"only {p.sample_size} impressions (< {min_sample})",
                )
            )

        prev = previous_scores.get(_key(p))
        if prev is not None and prev > 0:
            change = abs(p.smoothed_score - prev) / prev
            if change > drift_threshold:
                alerts.append(
                    GuardrailAlert(
                        kind=DRIFT,
                        dimension=p.dimension,
                        vertical=p.vertical,
                        value=p.value,
                        detail=f"score moved {change:.0%} ({prev:.4f} → {p.smoothed_score:.4f})",
                    )
                )

    return alerts


def snapshot_scores(performances: list[DimensionPerformance]) -> dict[str, float]:
    """Snapshot current scores for the next run's drift comparison."""
    return {_key(p): p.smoothed_score for p in performances}
