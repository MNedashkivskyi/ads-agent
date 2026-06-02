from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adcopilot.application.ports.measurement import UploadResult
from adcopilot.application.use_cases.upload_offline_conversions import (
    upload_offline_conversions,
)
from adcopilot.domain.conversion_outcome import ConversionOutcome, OutcomeStatus, UploadStatus


def _won(action_id: int | None, *, gclid="G", ext=None) -> ConversionOutcome:
    o = ConversionOutcome(account_id="acc-1", gclid=gclid, conversion_action_id=action_id, external_id=ext)
    o.mark_won(value=100.0, occurred_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC))
    return o


class FakeOutcomeRepo:
    def __init__(self, outcomes):
        self._outcomes = outcomes
        self.uploaded_ids = None
        self.failed = None

    async def list_uploadable(self, account_id, *, limit=500):
        return self._outcomes

    async def mark_uploaded(self, ids, when):
        self.uploaded_ids = list(ids)

    async def mark_failed(self, ids, error):
        self.failed = (list(ids), error)


class FakeUploadRepo:
    def __init__(self):
        self.records = []

    async def record(self, rec):
        self.records.append(rec)


class FakeUploader:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def upload_click_conversions(self, refresh_token, customer_id, conversions, *, validate_only=False):
        self.calls.append((conversions, validate_only))
        return self.result


async def _run(outcomes, result, *, validate_only=False):
    repo = FakeOutcomeRepo(outcomes)
    uploads = FakeUploadRepo()
    uploader = FakeUploader(result)
    out = await upload_offline_conversions(
        account_id="acc-1",
        customer_id="123-456-7890",
        refresh_token="rt",
        outcome_repo=repo,
        upload_repo=uploads,
        uploader=uploader,
        validate_only=validate_only,
    )
    return out, repo, uploads, uploader


@pytest.mark.asyncio
async def test_happy_marks_uploaded_and_audits() -> None:
    outcomes = [_won(11, ext="a"), _won(12, ext="b")]
    res, repo, uploads, uploader = await _run(
        outcomes, UploadResult.build(received=2, succeeded=2)
    )
    assert res.succeeded == 2
    # All eligible marked uploaded; conversions carried order_id for dedup.
    assert set(repo.uploaded_ids) == {o.id for o in outcomes}
    convs = uploader.calls[0][0]
    assert {c.order_id for c in convs} == {"a", "b"}
    assert uploads.records and uploads.records[0].succeeded is True


@pytest.mark.asyncio
async def test_skips_outcomes_without_conversion_action() -> None:
    outcomes = [_won(11, ext="a"), _won(None, ext="no-action")]
    res, repo, uploads, uploader = await _run(
        outcomes, UploadResult.build(received=1, succeeded=1)
    )
    convs = uploader.calls[0][0]
    assert len(convs) == 1  # the action-less outcome is not uploaded
    assert res.received == 1


@pytest.mark.asyncio
async def test_validate_only_does_not_mutate_state() -> None:
    outcomes = [_won(11, ext="a")]
    res, repo, uploads, uploader = await _run(
        outcomes, UploadResult.build(received=1, succeeded=1, validate_only=True), validate_only=True
    )
    assert uploader.calls[0][1] is True  # validate_only threaded through
    assert repo.uploaded_ids is None  # not marked uploaded on a dry run
    assert uploads.records[0].validate_only is True


@pytest.mark.asyncio
async def test_failure_marks_failed_for_retry() -> None:
    outcomes = [_won(11, ext="a")]
    res, repo, uploads, uploader = await _run(
        outcomes, UploadResult.build(received=1, succeeded=0, errors=["invalid gclid"])
    )
    assert repo.uploaded_ids is None
    assert repo.failed is not None
    assert "invalid gclid" in repo.failed[1]
    assert uploads.records[0].succeeded is False


@pytest.mark.asyncio
async def test_nothing_uploadable_skips_call() -> None:
    res, repo, uploads, uploader = await _run([], UploadResult.build(received=0, succeeded=0))
    assert res.received == 0
    assert uploader.calls == []  # no API call when there's nothing to send
