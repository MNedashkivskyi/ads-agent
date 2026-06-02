from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adcopilot.application.ports.measurement import UploadResult
from adcopilot.application.use_cases.upload_conversion_adjustments import (
    upload_conversion_adjustments,
)
from adcopilot.domain.conversion_outcome import ConversionOutcome, UploadStatus


def _uploaded_won(action_id=11, ext="a") -> ConversionOutcome:
    o = ConversionOutcome(account_id="acc-1", gclid="G", conversion_action_id=action_id, external_id=ext)
    o.mark_won(value=100.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    o.upload_status = UploadStatus.UPLOADED
    return o


class FakeRepo:
    def __init__(self, outcomes):
        self._outcomes = outcomes
        self.saved = []

    async def list_needing_adjustment(self, account_id, *, limit=500):
        return [o for o in self._outcomes if o.needs_adjustment()]

    async def save(self, o):
        self.saved.append(o)


class FakeUploadRepo:
    def __init__(self):
        self.records = []

    async def record(self, rec):
        self.records.append(rec)


class FakeUploader:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def upload_conversion_adjustments(self, rt, cid, adjustments, *, validate_only=False):
        self.calls.append((adjustments, validate_only))
        return self.result


async def _run(outcomes, result, *, validate_only=False):
    repo = FakeRepo(outcomes)
    uploads = FakeUploadRepo()
    uploader = FakeUploader(result)
    out = await upload_conversion_adjustments(
        account_id="acc-1",
        customer_id="123",
        refresh_token="rt",
        outcome_repo=repo,
        upload_repo=uploads,
        uploader=uploader,
        validate_only=validate_only,
    )
    return out, repo, uploads, uploader


@pytest.mark.asyncio
async def test_restatement_uploaded_and_cleared() -> None:
    o = _uploaded_won()
    o.restate(250.0)
    res, repo, uploads, uploader = await _run([o], UploadResult.build(received=1, succeeded=1))
    adj = uploader.calls[0][0][0]
    assert adj.adjustment_type == "RESTATEMENT"
    assert adj.restatement_value == 250.0
    assert adj.order_id == "a"
    assert repo.saved and repo.saved[0].needs_adjustment() is False  # cleared
    assert uploads.records[0].kind == "ADJUSTMENT"


@pytest.mark.asyncio
async def test_retraction_has_no_restatement_value() -> None:
    o = _uploaded_won()
    o.retract()
    res, repo, uploads, uploader = await _run([o], UploadResult.build(received=1, succeeded=1))
    adj = uploader.calls[0][0][0]
    assert adj.adjustment_type == "RETRACTION"
    assert adj.restatement_value is None


@pytest.mark.asyncio
async def test_validate_only_does_not_clear_pending() -> None:
    o = _uploaded_won()
    o.restate(250.0)
    res, repo, uploads, uploader = await _run(
        [o], UploadResult.build(received=1, succeeded=1, validate_only=True), validate_only=True
    )
    assert uploader.calls[0][1] is True
    assert repo.saved == []  # not cleared on dry-run
    assert o.needs_adjustment() is True


@pytest.mark.asyncio
async def test_nothing_pending_skips_call() -> None:
    res, repo, uploads, uploader = await _run([_uploaded_won()], UploadResult.build(received=0, succeeded=0))
    assert uploader.calls == []
    assert res.received == 0
