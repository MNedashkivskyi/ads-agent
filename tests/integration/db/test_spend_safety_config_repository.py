"""Integration tests for the spend-safety config repository.

Requires PostgreSQL (TEST_DATABASE_URL). db_session creates tables + rolls back.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.spend_safety import SpendSafetyConfig
from adcopilot.infrastructure.db.repositories.spend_safety_config_repository import (
    SpendSafetyConfigRepository,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_upsert_and_get_round_trip(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    repo = SpendSafetyConfigRepository(db_session)

    assert await repo.get(account_id) is None

    config = SpendSafetyConfig(
        account_id=account_id,
        monthly_spend_cap_micros=5_000_000_000,
        daily_spend_cap_micros=200_000_000,
        per_campaign_daily_cap_micros=80_000_000,
        max_budget_increase_pct=30.0,
        warning_threshold_pct=75.0,
        auto_pause_enabled=True,
        currency_code="PLN",
    )
    await repo.upsert(config)
    await db_session.flush()

    got = await repo.get(account_id)
    assert got is not None
    assert got.monthly_spend_cap_micros == 5_000_000_000
    assert got.per_campaign_daily_cap_micros == 80_000_000
    assert got.max_budget_increase_pct == 30.0
    assert got.auto_pause_enabled is True
    assert got.is_configured() is True


@pytest.mark.asyncio
async def test_upsert_overwrites(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    repo = SpendSafetyConfigRepository(db_session)

    await repo.upsert(SpendSafetyConfig(account_id=account_id, monthly_spend_cap_micros=1_000_000))
    await db_session.flush()
    await repo.upsert(
        SpendSafetyConfig(account_id=account_id, monthly_spend_cap_micros=2_000_000, auto_pause_enabled=True)
    )
    await db_session.flush()

    got = await repo.get(account_id)
    assert got is not None
    assert got.monthly_spend_cap_micros == 2_000_000
    assert got.auto_pause_enabled is True
