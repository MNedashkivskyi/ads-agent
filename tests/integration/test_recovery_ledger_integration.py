"""Integration test: SqlRecoveryLedgerRepository against real Postgres.

Unit tests cover the pure reconciliation math; this exercises the new repo SQL the
settle task relies on — recovered_total_micros, list_due_for_settlement (the
method/measured_at/applied_at filter), and settle() flipping projected → measured.
Requires TEST_DATABASE_URL.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId, GoogleAdsAccount, PlanTier, User, UserId
from adcopilot.infrastructure.db.repositories.audit_repository import SqlRecoveryLedgerRepository
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)
from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository


async def _seed_account(db_session: AsyncSession) -> AccountId:
    user_id = UserId(str(uuid.uuid4()))
    await SqlUserRepository(db_session).save(
        User(
            id=user_id,
            email=f"recovery-{uuid.uuid4()}@example.com",
            telegram_chat_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            plan=PlanTier.STARTER,
        )
    )
    account_id = AccountId(str(uuid.uuid4()))
    await SqlGoogleAdsAccountRepository(db_session).save(
        GoogleAdsAccount(
            id=account_id,
            user_id=user_id,
            customer_id="1112223334",
            descriptive_name="Recovery Test",
            currency="PLN",
            timezone="Europe/Warsaw",
            is_manager=False,
            write_enabled=True,
            connected_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    return account_id


@pytest.mark.integration
async def test_create_total_due_and_settle(db_session: AsyncSession) -> None:
    account_id = await _seed_account(db_session)
    ledger = SqlRecoveryLedgerRepository(db_session)

    e1 = await ledger.create(
        account_id=str(account_id),
        method="projected",
        recommendation_id=str(uuid.uuid4()),
        realized_saving_micros=300_000_000,
        baseline_metric={"projected_micros": 300_000_000, "campaign_id": 1},
    )
    e2 = await ledger.create(
        account_id=str(account_id),
        method="projected",
        realized_saving_micros=100_000_000,
        baseline_metric={"projected_micros": 100_000_000},
    )

    # The meter sums every entry's realised saving (projected counts immediately).
    assert await ledger.recovered_total_micros(str(account_id)) == 400_000_000

    # Both are projected + unmeasured, so both are due before any future cutoff.
    future = datetime.now(UTC) + timedelta(days=1)
    due_ids = {d.id for d in await ledger.list_due_for_settlement(before=future)}
    assert e1.id in due_ids
    assert e2.id in due_ids

    # Settle e1 to a measured value.
    await ledger.settle(e1.id, realized_saving_micros=250_000_000, measured_at=datetime.now(UTC))
    settled = await ledger.get(e1.id)
    assert settled is not None
    assert settled.method == "measured"
    assert settled.measured_at is not None
    assert settled.realized_saving_micros == 250_000_000

    # e1 is no longer due (measured); e2 still is.
    due_after = {d.id for d in await ledger.list_due_for_settlement(before=future)}
    assert e1.id not in due_after
    assert e2.id in due_after

    # Total now reflects the reconciled value (250M + 100M).
    assert await ledger.recovered_total_micros(str(account_id)) == 350_000_000
