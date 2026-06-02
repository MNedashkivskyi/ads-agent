"""Ports for the measurement upload boundary (Phase 1).

Defines the value objects exchanged with Google Ads and the upload port, so
use cases depend on an interface, not the SDK. The adapter lives in
infrastructure/google_ads/measurement_mutations_adapter.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class OfflineConversion:
    """One click-attributed conversion to upload (Offline Conversion Import).

    Exactly one of gclid/gbraid/wbraid should be set (click attribution); hashed
    identifiers may additionally be supplied for Enhanced Conversions for Leads.
    ``conversion_date_time`` must be ``"yyyy-mm-dd hh:mm:ss+hh:mm"`` (the format
    Google requires) in the account's timezone.
    """

    conversion_action_id: int
    conversion_date_time: str
    conversion_value: float
    currency_code: str = "PLN"
    gclid: str | None = None
    gbraid: str | None = None
    wbraid: str | None = None
    hashed_email: str | None = None
    hashed_phone: str | None = None
    order_id: str | None = None


@dataclass
class ConversionAdjustment:
    """A correction to an already-uploaded conversion (keyed by order_id).

    ``adjustment_type`` is "RESTATEMENT" (change value) or "RETRACTION" (cancel).
    ``restatement_value`` is required for restatements.
    """

    conversion_action_id: int
    order_id: str
    adjustment_type: str
    adjustment_date_time: str
    restatement_value: float | None = None
    currency_code: str = "PLN"


@dataclass
class UploadResult:
    received: int
    succeeded: int
    failed: int
    errors: list[str] = field(default_factory=list)
    validate_only: bool = False

    @classmethod
    def build(
        cls,
        *,
        received: int,
        succeeded: int,
        errors: list[str] | None = None,
        validate_only: bool = False,
    ) -> UploadResult:
        return cls(
            received=received,
            succeeded=succeeded,
            failed=max(received - succeeded, 0),
            errors=errors or [],
            validate_only=validate_only,
        )


class MeasurementUploadPort(Protocol):
    """Uploads offline conversions to Google Ads."""

    async def upload_click_conversions(
        self,
        refresh_token: str,
        customer_id: str,
        conversions: list[OfflineConversion],
        *,
        validate_only: bool = False,
    ) -> UploadResult: ...

    async def upload_conversion_adjustments(
        self,
        refresh_token: str,
        customer_id: str,
        adjustments: list[ConversionAdjustment],
        *,
        validate_only: bool = False,
    ) -> UploadResult: ...
