"""Reconcile GA4 conversions against Google Ads conversions (Phase 6).

A large gap between what GA4 and Google Ads report usually means broken or
double-counted tracking — a measurement red flag worth surfacing. Pure logic so
it's easy to test; the endpoint supplies the two totals.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# Relative gap (vs the larger side) under which we treat the two as aligned.
_ALIGNED_THRESHOLD_PCT = 15.0


class ReconciliationVerdict(str, Enum):
    NO_DATA = "NO_DATA"
    ALIGNED = "ALIGNED"
    GA4_HIGHER = "GA4_HIGHER"
    ADS_HIGHER = "ADS_HIGHER"


@dataclass
class ReconciliationResult:
    ga4_conversions: float
    ads_conversions: float
    discrepancy_pct: float  # (ga4 - ads) / max(ga4, ads) * 100; signed
    verdict: ReconciliationVerdict


def reconcile_conversions(*, ga4_conversions: float, ads_conversions: float) -> ReconciliationResult:
    ga4 = max(ga4_conversions, 0.0)
    ads = max(ads_conversions, 0.0)
    denom = max(ga4, ads)
    if denom <= 0:
        return ReconciliationResult(ga4, ads, 0.0, ReconciliationVerdict.NO_DATA)

    discrepancy = round((ga4 - ads) / denom * 100, 1)
    if abs(discrepancy) <= _ALIGNED_THRESHOLD_PCT:
        verdict = ReconciliationVerdict.ALIGNED
    elif discrepancy > 0:
        verdict = ReconciliationVerdict.GA4_HIGHER
    else:
        verdict = ReconciliationVerdict.ADS_HIGHER
    return ReconciliationResult(ga4, ads, discrepancy, verdict)
