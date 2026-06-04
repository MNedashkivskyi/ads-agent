"""Compare actual performance to the account's configured targets.

`business_economics.target_cpa` / `target_roas` are captured at onboarding but
never compared against actuals. This pure function produces an "are we hitting
target?" verdict that the weekly insight (and any report) can surface.
"""

from __future__ import annotations

from dataclasses import dataclass

# How far past target still counts as "on track" (accounts for normal variance).
_TOLERANCE_PCT = 10.0


@dataclass(frozen=True)
class TargetComparison:
    cpa_vs_target_pct: float | None  # +ve = actual CPA above target (worse); None if N/A
    roas_vs_target_pct: float | None  # +ve = actual ROAS above target (better); None if N/A
    on_track: bool

    def as_dict(self) -> dict:
        return {
            "cpa_vs_target_pct": self.cpa_vs_target_pct,
            "roas_vs_target_pct": self.roas_vs_target_pct,
            "on_track": self.on_track,
        }


def compare_to_targets(
    actual_cpa: float | None,
    actual_roas: float | None,
    *,
    target_cpa: float | None,
    target_roas: float | None,
    tolerance_pct: float = _TOLERANCE_PCT,
) -> TargetComparison | None:
    """Return the actual-vs-target comparison, or None when no targets are set.

    CPA is "good" when actual is at/below target; ROAS is "good" when actual is
    at/above target. ``on_track`` requires every configured target to be met
    within ``tolerance_pct``.
    """
    if not target_cpa and not target_roas:
        return None

    cpa_pct: float | None = None
    if target_cpa and actual_cpa is not None:
        cpa_pct = round((actual_cpa - target_cpa) / target_cpa * 100, 1)

    roas_pct: float | None = None
    if target_roas and actual_roas is not None:
        roas_pct = round((actual_roas - target_roas) / target_roas * 100, 1)

    cpa_ok = cpa_pct is None or cpa_pct <= tolerance_pct
    roas_ok = roas_pct is None or roas_pct >= -tolerance_pct
    return TargetComparison(cpa_pct, roas_pct, cpa_ok and roas_ok)
