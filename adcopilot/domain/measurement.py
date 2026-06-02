"""Measurement Foundation — domain types for the measurement-health diagnostic.

Phase 0 of the measurement foundation. A read-only diagnostic that scores how
well an account is set up to feed Smart Bidding (tCPA/tROAS/Max Conversions):
the better the conversion signal, the better the bidding. Later phases
(Offline Conversion Import, Enhanced Conversions, Consent Mode v2, value-based
conversions, GA4 import) deepen the signals each sub-score reports on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class MeasurementStatus(str, Enum):
    """Traffic-light status for the overall report and each sub-score."""

    HEALTHY = "HEALTHY"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    MISSING = "MISSING"


# Stable keys for the six sub-scores. The frontend keys cards off these.
SUBSCORE_KEYS = (
    "conversion_actions",
    "value_tracking",
    "enhanced_conversions",
    "consent_mode_v2",
    "ga4_link",
    "oci_readiness",
)


@dataclass
class MeasurementSubScore:
    key: str
    label: str  # Polish display label
    status: MeasurementStatus
    detail: str  # Polish remediation / explanation


@dataclass
class ConversionActionSummary:
    name: str
    category: str
    status: str
    all_conversions: float
    health: str  # HEALTHY | STALE | DISABLED


@dataclass
class MeasurementHealthReport:
    overall_status: MeasurementStatus
    subscores: list[MeasurementSubScore] = field(default_factory=list)
    conversion_actions: list[ConversionActionSummary] = field(default_factory=list)
