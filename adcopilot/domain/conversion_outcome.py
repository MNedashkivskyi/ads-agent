"""Domain types for the conversion-ingestion core (Phase 1).

A ``ConversionOutcome`` is a real-world result (a lead that became qualified /
won, or an offline sale) captured by us and destined for Google Ads via Offline
Conversion Import or Enhanced Conversions for Leads. It carries the click
identifier (gclid / gbraid / wbraid) and/or hashed first-party identifiers
needed to attribute the conversion, its monetary value, and its lifecycle +
upload state.

This phase defines the model + transitions only; the upload pipeline (Phase 2)
and Enhanced Conversions (Phase 3) consume it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class OutcomeStatus(str, Enum):
    """Lifecycle of a captured outcome (mirrors a simple CRM funnel)."""

    NEW = "NEW"
    QUALIFIED = "QUALIFIED"
    WON = "WON"
    LOST = "LOST"


class UploadStatus(str, Enum):
    """Whether the outcome has been pushed to Google Ads."""

    PENDING = "PENDING"  # not yet eligible / not yet sent
    UPLOADED = "UPLOADED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"  # e.g. LOST outcomes are not uploaded


class AdjustmentType(str, Enum):
    """A correction to an already-uploaded conversion."""

    RESTATEMENT = "RESTATEMENT"  # change the conversion value
    RETRACTION = "RETRACTION"  # cancel the conversion (e.g. lead later lost)


# Only WON outcomes carry a positive conversion worth uploading.
UPLOADABLE_STATUSES = frozenset({OutcomeStatus.WON})


@dataclass
class ConversionOutcome:
    account_id: str
    # Attribution — at least one click id (OCI) or a hashed identifier (ECL).
    gclid: str | None = None
    gbraid: str | None = None
    wbraid: str | None = None
    hashed_email: str | None = None
    hashed_phone: str | None = None
    # Which Google Ads conversion action this maps to (set when configured).
    conversion_action_id: int | None = None
    # Monetary value of the outcome (set when WON).
    value: float | None = None
    currency_code: str = "PLN"
    # Lifecycle + upload state.
    status: OutcomeStatus = OutcomeStatus.NEW
    upload_status: UploadStatus = UploadStatus.PENDING
    occurred_at: datetime | None = None
    uploaded_at: datetime | None = None
    last_error: str | None = None
    # Client-side identifier for idempotency / dedup (e.g. CRM lead id).
    external_id: str | None = None
    # A pending correction to an already-uploaded conversion (Phase 2b).
    pending_adjustment: str | None = None  # AdjustmentType value or None
    adjusted_at: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def has_click_identifier(self) -> bool:
        return any((self.gclid, self.gbraid, self.wbraid))

    def has_hashed_identifier(self) -> bool:
        return any((self.hashed_email, self.hashed_phone))

    def is_uploadable(self) -> bool:
        """A WON outcome with attribution + value + occurrence time, not yet sent."""
        return (
            self.status in UPLOADABLE_STATUSES
            and self.upload_status in (UploadStatus.PENDING, UploadStatus.FAILED)
            and (self.has_click_identifier() or self.has_hashed_identifier())
            and self.value is not None
            and self.occurred_at is not None
        )

    def mark_qualified(self) -> None:
        self.status = OutcomeStatus.QUALIFIED
        self.updated_at = datetime.now(UTC)

    def mark_won(self, value: float, occurred_at: datetime, currency_code: str | None = None) -> None:
        if value < 0:
            raise ValueError("Conversion value cannot be negative")
        self.status = OutcomeStatus.WON
        self.value = value
        self.occurred_at = occurred_at
        if currency_code:
            self.currency_code = currency_code
        self.upload_status = UploadStatus.PENDING
        self.updated_at = datetime.now(UTC)

    def mark_lost(self) -> None:
        self.status = OutcomeStatus.LOST
        self.upload_status = UploadStatus.SKIPPED
        self.updated_at = datetime.now(UTC)

    # --- Phase 2b: adjustments to an already-uploaded conversion -----------

    def restate(self, new_value: float) -> None:
        """Change the value of an already-uploaded WON conversion."""
        if new_value < 0:
            raise ValueError("Conversion value cannot be negative")
        if self.upload_status is not UploadStatus.UPLOADED or self.status is not OutcomeStatus.WON:
            raise ValueError("Only an uploaded WON conversion can be restated")
        self.value = new_value
        self.pending_adjustment = AdjustmentType.RESTATEMENT.value
        self.updated_at = datetime.now(UTC)

    def retract(self) -> None:
        """Cancel an already-uploaded conversion (lead later lost / refunded)."""
        if self.upload_status is not UploadStatus.UPLOADED:
            raise ValueError("Only an uploaded conversion can be retracted")
        self.status = OutcomeStatus.LOST
        self.pending_adjustment = AdjustmentType.RETRACTION.value
        self.updated_at = datetime.now(UTC)

    def needs_adjustment(self) -> bool:
        return self.pending_adjustment is not None

    def mark_adjusted(self) -> None:
        self.pending_adjustment = None
        self.adjusted_at = datetime.now(UTC)
        self.updated_at = datetime.now(UTC)


@dataclass
class ConversionUploadRecord:
    """Audit row for one upload attempt (batch), success or failure."""

    account_id: str
    kind: str  # "OFFLINE_CONVERSION" | "ENHANCED_CONVERSION" | "ADJUSTMENT"
    outcome_count: int
    validate_only: bool
    succeeded: bool
    failed_count: int = 0
    error_summary: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
