"""Integration tests for the conversion-outcome repositories.

Requires a running PostgreSQL instance (TEST_DATABASE_URL env var). The
db_session fixture creates all tables and rolls back per test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.conversion_outcome import (
    ConversionOutcome,
    ConversionUploadRecord,
    OutcomeStatus,
    UploadStatus,
)
from adcopilot.infrastructure.db.repositories.conversion_outcome_repository import (
    ConversionOutcomeRepository,
    ConversionUploadRepository,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_save_and_uploadable_lifecycle(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    repo = ConversionOutcomeRepository(db_session)

    outcome = ConversionOutcome(account_id=account_id, gclid="GCL_ABC", external_id="lead-1")
    await repo.save(outcome)
    await db_session.flush()

    # NEW outcome is not uploadable.
    assert await repo.list_uploadable(account_id) == []

    # Winning it (with value + time) makes it uploadable.
    outcome.mark_won(value=1500.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    await repo.save(outcome)
    await db_session.flush()

    uploadable = await repo.list_uploadable(account_id)
    assert len(uploadable) == 1
    assert uploadable[0].value == 1500.0
    assert uploadable[0].status is OutcomeStatus.WON


@pytest.mark.asyncio
async def test_dedup_by_external_id(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    repo = ConversionOutcomeRepository(db_session)

    o = ConversionOutcome(account_id=account_id, gclid="G1", external_id="crm-42")
    await repo.save(o)
    await db_session.flush()

    found = await repo.get_by_external_id(account_id, "crm-42")
    assert found is not None
    assert found.external_id == "crm-42"
    assert await repo.get_by_external_id(account_id, "does-not-exist") is None


@pytest.mark.asyncio
async def test_mark_uploaded_and_failed(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    repo = ConversionOutcomeRepository(db_session)

    o = ConversionOutcome(account_id=account_id, gclid="G2")
    o.mark_won(value=10.0, occurred_at=datetime(2026, 6, 1, tzinfo=UTC))
    await repo.save(o)
    await db_session.flush()

    await repo.mark_uploaded([o.id], datetime.now(UTC))
    await db_session.flush()
    reloaded = await repo.get(o.id)
    assert reloaded is not None
    assert reloaded.upload_status is UploadStatus.UPLOADED
    # Uploaded outcomes are no longer in the uploadable queue.
    assert await repo.list_uploadable(account_id) == []


@pytest.mark.asyncio
async def test_upload_audit_record(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    uploads = ConversionUploadRepository(db_session)

    await uploads.record(
        ConversionUploadRecord(
            account_id=account_id,
            kind="OFFLINE_CONVERSION",
            outcome_count=3,
            validate_only=True,
            succeeded=True,
        )
    )
    await db_session.flush()  # no exception == persisted
