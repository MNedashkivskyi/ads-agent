"""upload_conversion_adjustments — push restate/retract corrections (Phase 2b).

Gathers UPLOADED outcomes with a pending adjustment (value changed → RESTATEMENT,
or cancelled → RETRACTION), uploads them keyed by order_id, audits, and clears
the pending flag on success. validate_only does a dry run without mutating state.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from adcopilot.application.ports.measurement import (
    ConversionAdjustment,
    MeasurementUploadPort,
    UploadResult,
)
from adcopilot.application.use_cases.upload_offline_conversions import _format_conversion_dt
from adcopilot.domain.conversion_outcome import ConversionOutcome, ConversionUploadRecord

logger = structlog.get_logger(__name__)


def _to_adjustment(o: ConversionOutcome, when: datetime) -> ConversionAdjustment:
    is_restatement = o.pending_adjustment == "RESTATEMENT"
    return ConversionAdjustment(
        conversion_action_id=int(o.conversion_action_id),  # caller guarantees not None
        order_id=o.external_id or str(o.id),
        adjustment_type=str(o.pending_adjustment),
        adjustment_date_time=_format_conversion_dt(when),
        restatement_value=float(o.value) if (is_restatement and o.value is not None) else None,
        currency_code=o.currency_code,
    )


async def upload_conversion_adjustments(
    *,
    account_id: str,
    customer_id: str,
    refresh_token: str,
    outcome_repo,
    upload_repo,
    uploader: MeasurementUploadPort,
    validate_only: bool = False,
    limit: int = 500,
) -> UploadResult:
    outcomes = await outcome_repo.list_needing_adjustment(account_id, limit=limit)
    eligible = [o for o in outcomes if o.conversion_action_id]
    if not eligible:
        return UploadResult.build(received=0, succeeded=0, validate_only=validate_only)

    now = datetime.now(UTC)
    adjustments = [_to_adjustment(o, now) for o in eligible]
    result = await uploader.upload_conversion_adjustments(
        refresh_token, customer_id, adjustments, validate_only=validate_only
    )

    await upload_repo.record(
        ConversionUploadRecord(
            account_id=account_id,
            kind="ADJUSTMENT",
            outcome_count=result.received,
            validate_only=validate_only,
            succeeded=result.failed == 0,
            failed_count=result.failed,
            error_summary=("; ".join(result.errors)[:1000] or None),
        )
    )

    if not validate_only and result.failed == 0:
        for o in eligible:
            o.mark_adjusted()
            await outcome_repo.save(o)

    logger.info(
        "conversion_adjustments_done",
        account_id=account_id,
        received=result.received,
        succeeded=result.succeeded,
        failed=result.failed,
        validate_only=validate_only,
    )
    return result
