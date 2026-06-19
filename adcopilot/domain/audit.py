"""Audit-funnel domain — the free Google Ads waste audit (Audit Funnel Phase 0).

A cold visitor connects their Google Ads account read-only; we scan it and
produce a conservative, evidence-backed monthly *waste* figure. These are the
aggregates the funnel persists: the (possibly anonymous) audit session, the
computed waste report, its individual findings, and the recovery ledger that
later tracks realised savings as fixes are applied.

Money is stored in micros (1 unit = 1_000_000 micros) to match the rest of the
codebase (``cost_micros``, ``budget_micros``, …).

Confidence tiers (see the Audit Funnel plan §3):
- ``CONFIRMED`` (Tier 1) — money provably spent for zero return; feeds the
  headline number.
- ``ESTIMATED`` (Tier 2) — likely overpayment; shown but labelled, never in the
  headline.
- ``QUALITATIVE`` (Tier 3) — measurement gaps / issues with no PLN value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

MICROS_PER_UNIT = 1_000_000


class AuditStatus(StrEnum):
    PENDING = "pending"  # connected, scan not started
    SCANNING = "scanning"  # scan in progress
    READY = "ready"  # report computed
    PROMOTED = "promoted"  # converted to a real account / trial
    EXPIRED = "expired"  # retention window elapsed (GDPR)
    FAILED = "failed"  # scan errored


class AuditSource(StrEnum):
    LANDING = "landing"  # public /audit landing page
    AGENCY = "agency"  # agency-initiated (prospecting)
    SHARE = "share"  # opened from a shared report link


class WasteCategory(StrEnum):
    SEARCHTERM_WASTE = "searchterm_waste"  # Tier 1
    KEYWORD_WASTE = "keyword_waste"  # Tier 1
    NEGATIVE_BLOCKABLE = "negative_blockable"  # Tier 1
    QS_OVERPAYMENT = "qs_overpayment"  # Tier 2 (estimated)
    MEASUREMENT_GAP = "measurement_gap"  # Tier 3 (no PLN value)
    ISSUE = "issue"  # Tier 3 (qualitative)


class FindingTier(StrEnum):
    CONFIRMED = "confirmed"  # feeds the headline number
    ESTIMATED = "estimated"  # shown, labelled, not in headline
    QUALITATIVE = "qualitative"  # no PLN value


class ReportConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LIMITED = "limited"  # too little data → no headline number


# The confirmed (Tier 1) categories that feed the headline waste figure.
HEADLINE_CATEGORIES: frozenset[WasteCategory] = frozenset(
    {
        WasteCategory.SEARCHTERM_WASTE,
        WasteCategory.KEYWORD_WASTE,
        WasteCategory.NEGATIVE_BLOCKABLE,
    }
)


@dataclass(frozen=True)
class AuditSession:
    """A (possibly anonymous) free-audit session keyed to a Google customer id."""

    id: str
    google_customer_id: str | None = None  # resolved during the scan (Phase 2)
    status: AuditStatus = AuditStatus.PENDING
    oauth_scope: str = "adwords-readonly"
    source: AuditSource = AuditSource.LANDING
    email: str | None = None
    user_id: str | None = None
    account_id: str | None = None
    agency_org_id: str | None = None  # set when an agency initiated this audit (Phase 5C)
    consent_at: datetime | None = None
    created_at: datetime | None = None
    expires_at: datetime | None = None

    @property
    def is_promoted(self) -> bool:
        return self.status is AuditStatus.PROMOTED or self.user_id is not None

    def is_expired(self, *, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at


@dataclass(frozen=True)
class WasteReport:
    """The computed audit result — headline waste plus measurement gap."""

    id: str
    window_start: date
    window_end: date
    total_spend_micros: int
    headline_waste_micros: int
    measurement_gap_pct: float
    confidence: ReportConfidence
    currency: str = "PLN"
    methodology_version: str = "1"
    audit_session_id: str | None = None
    account_id: str | None = None
    computed_at: datetime | None = None

    @property
    def annual_waste_micros(self) -> int:
        """Headline monthly waste projected over a year (the red shock number)."""
        return self.headline_waste_micros * 12

    @property
    def waste_pct(self) -> float:
        """Headline waste as a share of window spend (0..1); 0 when spend is 0."""
        if self.total_spend_micros <= 0:
            return 0.0
        return self.headline_waste_micros / self.total_spend_micros


@dataclass(frozen=True)
class WasteFinding:
    """One categorised finding within a report; ``evidence`` carries the proof."""

    id: str
    report_id: str
    category: WasteCategory
    tier: FindingTier
    title: str
    severity: str = "MEDIUM"
    amount_micros: int | None = None
    evidence: dict[str, object] = field(default_factory=dict)
    recommendation_id: str | None = None


@dataclass(frozen=True)
class RecoveryLedgerEntry:
    """A realised (or projected) saving from applying a fix — powers the meter."""

    id: str
    account_id: str
    applied_at: datetime
    method: str = "projected"  # "measured" | "projected"
    finding_id: str | None = None
    recommendation_id: str | None = None
    baseline_metric: dict[str, object] = field(default_factory=dict)
    realized_saving_micros: int | None = None
    measured_at: datetime | None = None
