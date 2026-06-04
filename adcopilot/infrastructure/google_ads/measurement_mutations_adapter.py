"""Google Ads measurement upload adapter (Phase 1).

Implements MeasurementUploadPort against ConversionUploadService. Always uses
``partial_failure=True`` so one bad row doesn't reject the batch, and supports
``validate_only=True`` for safe dry-runs (validate without persisting).

The proto round-trip is exercised live (validate_only) on dev; the response
interpretation (`_interpret`) is pure and unit-tested.
"""

from __future__ import annotations

from typing import Any

import structlog

from adcopilot.application.ports.measurement import (
    ConversionAdjustment,
    OfflineConversion,
    UploadResult,
)
from adcopilot.config import Settings
from adcopilot.domain.exceptions import (
    GoogleAdsAuthError,
    GoogleAdsRateLimited,
    GoogleAdsUnavailable,
)
from adcopilot.infrastructure.google_ads.client import (
    GoogleAdsClientAdapter,
    is_google_auth_error,
    is_rate_limit_error,
)
from adcopilot.infrastructure.google_ads.resilience import throttled_adapter

logger = structlog.get_logger(__name__)


def _wrap(operation: str, exc: Exception) -> Exception:
    if is_google_auth_error(exc):
        return GoogleAdsAuthError(str(exc))
    if is_rate_limit_error(exc):
        return GoogleAdsRateLimited(f"{operation} rate-limited: {exc}")
    return GoogleAdsUnavailable(f"{operation} failed: {exc}")


def _is_success_result(result: Any) -> bool:
    """A successful conversion result echoes attribution fields; a failed
    operation's result message is empty."""
    return bool(
        getattr(result, "conversion_action", "")
        or getattr(result, "gclid", "")
        or getattr(result, "gbraid", "")
        or getattr(result, "wbraid", "")
    )


def _extract_partial_failure_messages(pfe: Any) -> list[str]:
    """Pull human-readable error messages out of a partial_failure_error.

    Tries to unpack the GoogleAdsFailure details; falls back to the top-level
    status message if detailed extraction isn't possible.
    """
    messages: list[str] = []
    for detail in getattr(pfe, "details", []) or []:
        try:
            from google.ads.googleads.errors import GoogleAdsFailure  # type: ignore

            failure = GoogleAdsFailure.deserialize(detail.value)
            for err in failure.errors:
                if getattr(err, "message", ""):
                    messages.append(err.message)
        except Exception:  # noqa: BLE001 — best-effort; fall back below
            continue
    if not messages:
        top = getattr(pfe, "message", "")
        if top:
            messages.append(top)
    return messages


@throttled_adapter
class GoogleAdsMeasurementUploadAdapter:
    """Implements MeasurementUploadPort against the real Google Ads API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = GoogleAdsClientAdapter(settings)

    def _build_client(self, refresh_token: str) -> Any:
        return self._client._build_client(refresh_token)

    @staticmethod
    def _interpret(response: Any, received: int, validate_only: bool) -> UploadResult:
        results = list(getattr(response, "results", []) or [])
        succeeded = sum(1 for r in results if _is_success_result(r))
        errors: list[str] = []
        pfe = getattr(response, "partial_failure_error", None)
        if pfe is not None and getattr(pfe, "code", 0) not in (0, None):
            errors = _extract_partial_failure_messages(pfe)
        # On success the API returns one result per accepted conversion; if it
        # returned none but we sent some and there was no error, assume all ok.
        if not results and not errors and received:
            succeeded = received
        return UploadResult.build(
            received=received, succeeded=succeeded, errors=errors, validate_only=validate_only
        )

    def _build_click_conversion(self, client: Any, cid: str, c: OfflineConversion) -> Any:
        ca_service = client.get_service("ConversionActionService")
        conversion = client.get_type("ClickConversion")
        conversion.conversion_action = ca_service.conversion_action_path(
            cid, c.conversion_action_id
        )
        conversion.conversion_date_time = c.conversion_date_time
        conversion.conversion_value = float(c.conversion_value)
        conversion.currency_code = c.currency_code
        if c.gclid:
            conversion.gclid = c.gclid
        elif c.gbraid:
            conversion.gbraid = c.gbraid
        elif c.wbraid:
            conversion.wbraid = c.wbraid
        if c.order_id:
            conversion.order_id = c.order_id
        # Enhanced Conversions for Leads (Phase 3): attach hashed identifiers.
        if c.hashed_email:
            identifier = client.get_type("UserIdentifier")
            identifier.hashed_email = c.hashed_email
            conversion.user_identifiers.append(identifier)
        if c.hashed_phone:
            identifier = client.get_type("UserIdentifier")
            identifier.hashed_phone_number = c.hashed_phone
            conversion.user_identifiers.append(identifier)
        return conversion

    async def upload_click_conversions(
        self,
        refresh_token: str,
        customer_id: str,
        conversions: list[OfflineConversion],
        *,
        validate_only: bool = False,
    ) -> UploadResult:
        received = len(conversions)
        if received == 0:
            return UploadResult.build(received=0, succeeded=0, validate_only=validate_only)
        try:
            client = self._build_client(refresh_token)
            service = client.get_service("ConversionUploadService")
            cid = customer_id.replace("-", "")
            request = client.get_type("UploadClickConversionsRequest")
            request.customer_id = cid
            request.conversions.extend(
                self._build_click_conversion(client, cid, c) for c in conversions
            )
            request.partial_failure = True
            request.validate_only = validate_only
            response = service.upload_click_conversions(request=request)
            result = self._interpret(response, received, validate_only)
            logger.info(
                "offline_conversions_uploaded",
                customer_id=customer_id,
                received=result.received,
                succeeded=result.succeeded,
                failed=result.failed,
                validate_only=validate_only,
            )
            return result
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("upload_click_conversions", exc) from exc

    def _build_adjustment(self, client: Any, cid: str, a: ConversionAdjustment) -> Any:
        ca_service = client.get_service("ConversionActionService")
        adjustment = client.get_type("ConversionAdjustment")
        adjustment.conversion_action = ca_service.conversion_action_path(
            cid, a.conversion_action_id
        )
        adjustment.adjustment_type = client.enums.ConversionAdjustmentTypeEnum[a.adjustment_type]
        adjustment.order_id = a.order_id
        adjustment.adjustment_date_time = a.adjustment_date_time
        if a.adjustment_type == "RESTATEMENT" and a.restatement_value is not None:
            adjustment.restatement_value.adjusted_value = float(a.restatement_value)
            adjustment.restatement_value.currency_code = a.currency_code
        return adjustment

    async def upload_conversion_adjustments(
        self,
        refresh_token: str,
        customer_id: str,
        adjustments: list[ConversionAdjustment],
        *,
        validate_only: bool = False,
    ) -> UploadResult:
        received = len(adjustments)
        if received == 0:
            return UploadResult.build(received=0, succeeded=0, validate_only=validate_only)
        try:
            client = self._build_client(refresh_token)
            service = client.get_service("ConversionAdjustmentUploadService")
            cid = customer_id.replace("-", "")
            request = client.get_type("UploadConversionAdjustmentsRequest")
            request.customer_id = cid
            request.conversion_adjustments.extend(
                self._build_adjustment(client, cid, a) for a in adjustments
            )
            request.partial_failure = True
            request.validate_only = validate_only
            response = service.upload_conversion_adjustments(request=request)
            result = self._interpret(response, received, validate_only)
            logger.info(
                "conversion_adjustments_uploaded",
                customer_id=customer_id,
                received=result.received,
                succeeded=result.succeeded,
                failed=result.failed,
                validate_only=validate_only,
            )
            return result
        except (GoogleAdsAuthError, GoogleAdsUnavailable):
            raise
        except Exception as exc:  # noqa: BLE001
            raise _wrap("upload_conversion_adjustments", exc) from exc
