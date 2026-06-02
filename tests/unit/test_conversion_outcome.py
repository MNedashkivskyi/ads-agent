from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adcopilot.domain.conversion_outcome import (
    ConversionOutcome,
    OutcomeStatus,
    UploadStatus,
)


def _new(**kw) -> ConversionOutcome:
    return ConversionOutcome(account_id="acc-1", gclid="GCL123", **kw)


def test_new_outcome_is_not_uploadable() -> None:
    o = _new()
    assert o.status is OutcomeStatus.NEW
    assert o.upload_status is UploadStatus.PENDING
    assert o.is_uploadable() is False  # not won, no value/time


def test_mark_won_makes_it_uploadable() -> None:
    o = _new()
    o.mark_won(value=1500.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC), currency_code="PLN")
    assert o.status is OutcomeStatus.WON
    assert o.value == 1500.0
    assert o.currency_code == "PLN"
    assert o.is_uploadable() is True


def test_won_without_attribution_is_not_uploadable() -> None:
    o = ConversionOutcome(account_id="acc-1")  # no gclid / hashed id
    o.mark_won(value=10.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    assert o.is_uploadable() is False


def test_mark_lost_is_skipped_and_not_uploadable() -> None:
    o = _new()
    o.mark_lost()
    assert o.status is OutcomeStatus.LOST
    assert o.upload_status is UploadStatus.SKIPPED
    assert o.is_uploadable() is False


def test_negative_value_rejected() -> None:
    o = _new()
    with pytest.raises(ValueError):
        o.mark_won(value=-1.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))


def test_restate_only_after_upload() -> None:
    o = _new()
    o.mark_won(value=100.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    # Not uploaded yet -> cannot restate.
    with pytest.raises(ValueError):
        o.restate(200.0)
    o.upload_status = UploadStatus.UPLOADED
    o.restate(200.0)
    assert o.value == 200.0
    assert o.needs_adjustment() is True
    assert o.pending_adjustment == "RESTATEMENT"
    o.mark_adjusted()
    assert o.needs_adjustment() is False
    assert o.adjusted_at is not None


def test_retract_only_after_upload() -> None:
    o = _new()
    o.mark_won(value=100.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        o.retract()
    o.upload_status = UploadStatus.UPLOADED
    o.retract()
    assert o.status is OutcomeStatus.LOST
    assert o.pending_adjustment == "RETRACTION"


def test_hashed_identifier_alone_satisfies_attribution() -> None:
    o = ConversionOutcome(account_id="acc-1", hashed_email="abc123")
    o.mark_won(value=5.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    assert o.has_click_identifier() is False
    assert o.has_hashed_identifier() is True
    assert o.is_uploadable() is True
