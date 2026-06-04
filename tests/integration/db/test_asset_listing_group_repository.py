"""Integration: asset-group + listing-group snapshot repo round-trip (SH0).

Requires PostgreSQL (TEST_DATABASE_URL). db_session creates tables + rolls back.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.entities import AccountId
from adcopilot.domain.snapshot import AssetGroupSnapshot, ListingGroupSnapshot, SnapshotId
from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository

pytestmark = pytest.mark.integration

_DAY = date(2026, 6, 3)


def _ag(account_id: str, ad_strength: str = "POOR") -> AssetGroupSnapshot:
    return AssetGroupSnapshot(
        id=SnapshotId(str(uuid.uuid4())),
        account_id=AccountId(account_id),
        snapshot_date=_DAY,
        asset_group_id=11,
        campaign_id=99,
        name="AG1",
        status="ENABLED",
        ad_strength=ad_strength,
        primary_status="ELIGIBLE",
        impressions=1000,
        clicks=50,
        cost_micros=2_000_000,
        conversions=3.0,
        conv_value=600.0,
    )


@pytest.mark.asyncio
async def test_asset_group_round_trip_and_upsert(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    repo = SqlSnapshotRepository(db_session)

    await repo.upsert_asset_groups(AccountId(account_id), [_ag(account_id)])
    await db_session.flush()

    loaded = await repo.load_asset_groups(AccountId(account_id), _DAY)
    assert len(loaded) == 1
    assert loaded[0].ad_strength == "POOR"

    # Re-upsert same (account, date, asset_group) updates rather than duplicates.
    await repo.upsert_asset_groups(AccountId(account_id), [_ag(account_id, ad_strength="GOOD")])
    await db_session.flush()
    loaded = await repo.load_asset_groups(AccountId(account_id), _DAY)
    assert len(loaded) == 1
    assert loaded[0].ad_strength == "GOOD"


@pytest.mark.asyncio
async def test_listing_group_round_trip(db_session: AsyncSession) -> None:
    account_id = str(uuid.uuid4())
    repo = SqlSnapshotRepository(db_session)

    lg = ListingGroupSnapshot(
        id=SnapshotId(str(uuid.uuid4())),
        account_id=AccountId(account_id),
        snapshot_date=_DAY,
        asset_group_id=11,
        campaign_id=99,
        listing_group_id=7,
        dimension_type="",
        case_value="",
        is_catch_all=True,
    )
    await repo.upsert_listing_groups(AccountId(account_id), [lg])
    await db_session.flush()

    loaded = await repo.load_listing_groups(AccountId(account_id), _DAY)
    assert len(loaded) == 1
    assert loaded[0].is_catch_all is True
