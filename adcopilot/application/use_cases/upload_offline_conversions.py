"""upload_offline_conversions — push WON outcomes to Google Ads (Phase 2).

Gathers uploadable outcomes (WON, attributed, valued, not yet sent), uploads
them via the measurement port, writes an audit row, and updates outcome upload
state. Always set order_id so Google de-duplicates on retry — that lets us
safely re-send a whole batch when a partial failure occurs without
double-counting the rows that already succeeded.

Supports ``validate_only`` (dry-run): the API validates without persisting and
we leave outcome state untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from adcopilot.application.ports.measurement import (
    MeasurementUploadPort,
    OfflineConversion,
    UploadResult,
)
from adcopilot.domain.conversion_outcome import ConversionOutcome, ConversionUploadRecord

logger = structlog.get_logger(__name__)


def _format_conversion_dt(dt: datetime) -> str:
    """Format as Google's required 'yyyy-mm-dd hh:mm:ss+hh:mm'."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    s = dt.strftime("%Y-%m-%d %H:%M:%S%z")  # e.g. '... +0000'
    # Insert the colon into the timezone offset: +0000 -> +00:00
    if len(s) >= 5 and s[-5] in "+-":
        s = s[:-2] + ":" + s[-2:]
    return s


def _to_offline_conversion(o: ConversionOutcome) -> OfflineConversion:
    return OfflineConversion(
        conversion_action_id=int(o.conversion_action_id),  # caller guarantees not None
        conversion_date_time=_format_conversion_dt(o.occurred_at),  # type: ignore[arg-type]
        conversion_value=float(o.value or 0.0),
        currency_code=o.currency_code,
        gclid=o.gclid,
        gbraid=o.gbraid,
        wbraid=o.wbraid,
        hashed_email=o.hashed_email,
        hashed_phone=o.hashed_phone,
        order_id=o.external_id or str(o.id),
    )


async def upload_offline_conversions(
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
    outcomes = await outcome_repo.list_uploadable(account_id, limit=limit)
    eligible = [o for o in outcomes if o.conversion_action_id]
    skipped = len(outcomes) - len(eligible)
    if skipped:
        logger.info(
            "offline_conversions_skipped_no_action", account_id=account_id, count=skipped
        )

    if not eligible:
        return UploadResult.build(received=0, succeeded=0, validate_only=validate_only)

    conversions = [_to_offline_conversion(o) for o in eligible]
    result = await uploader.upload_click_conversions(
        refresh_token, customer_id, conversions, validate_only=validate_only
    )

    await upload_repo.record(
        ConversionUploadRecord(
            account_id=account_id,
            kind="OFFLINE_CONVERSION",
            outcome_count=result.received,
            validate_only=validate_only,
            succeeded=result.failed == 0,
            failed_count=result.failed,
            error_summary=("; ".join(result.errors)[:1000] or None),
        )
    )

    if not validate_only:
        ids = [o.id for o in eligible]
        if result.failed == 0:
            await outcome_repo.mark_uploaded(ids, datetime.now(UTC))
        else:
            # Can't map partial-failure indices reliably; mark the batch FAILED so
            # it retries. order_id makes the retry idempotent on Google's side.
            await outcome_repo.mark_failed(ids, "; ".join(result.errors) or "partial failure")

    logger.info(
        "offline_conversions_upload_done",
        account_id=account_id,
        received=result.received,
        succeeded=result.succeeded,
        failed=result.failed,
        validate_only=validate_only,
    )
    return result
