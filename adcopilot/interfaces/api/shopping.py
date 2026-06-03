"""Shopping / Performance Max health API (breadth).

Surfaces channel-aware ingestion: per-campaign asset-group health (ad strength,
serving status) and listing-group coverage for the account's PMax/Shopping
campaigns, from the latest snapshot.
"""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["shopping"])


class AssetGroupHealth(BaseModel):
    asset_group_id: int
    name: str
    ad_strength: str
    primary_status: str
    cost_pln: float
    conv_value: float


class PMaxCampaignHealth(BaseModel):
    campaign_id: int
    name: str
    channel_type: str
    cost_pln: float
    conv_value: float
    roas: float | None
    asset_groups: list[AssetGroupHealth]
    listing_group_count: int
    catch_all_only: bool


class ShoppingHealthResponse(BaseModel):
    snapshot_date: str | None
    campaigns: list[PMaxCampaignHealth]


@router.get("/{user_id}/shopping/health", response_model=ShoppingHealthResponse)
async def get_shopping_health(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ShoppingHealthResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.detection.channel import is_pmax_or_shopping
    from adcopilot.domain.entities import AccountId
    from adcopilot.infrastructure.db.repositories.snapshot_repository import SqlSnapshotRepository
    from adcopilot.interfaces.api.measurement import _resolve_account

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            repo = SqlSnapshotRepository(session)
            snap_date = await repo.get_latest_snapshot_date(AccountId(str(account.id)))
            if snap_date is None:
                return ShoppingHealthResponse(snapshot_date=None, campaigns=[])

            snapshot = await repo.load_snapshot(AccountId(str(account.id)), snap_date)
            asset_groups = await repo.load_asset_groups(AccountId(str(account.id)), snap_date)
            listing_groups = await repo.load_listing_groups(AccountId(str(account.id)), snap_date)

            ags_by_campaign: dict[int, list] = {}
            for ag in asset_groups:
                ags_by_campaign.setdefault(ag.campaign_id, []).append(ag)
            lgs_by_campaign: dict[int, list] = {}
            for lg in listing_groups:
                lgs_by_campaign.setdefault(lg.campaign_id, []).append(lg)

            campaigns: list[PMaxCampaignHealth] = []
            for c in snapshot.campaigns:
                if not is_pmax_or_shopping(c.channel_type):
                    continue
                roas = (
                    round((c.conv_value * 1_000_000) / c.cost_micros, 2)
                    if c.cost_micros > 0
                    else None
                )
                lgs = lgs_by_campaign.get(c.campaign_id, [])
                campaigns.append(
                    PMaxCampaignHealth(
                        campaign_id=c.campaign_id,
                        name=c.name,
                        channel_type=c.channel_type,
                        cost_pln=round(c.cost_micros / 1_000_000, 2),
                        conv_value=round(c.conv_value, 2),
                        roas=roas,
                        asset_groups=[
                            AssetGroupHealth(
                                asset_group_id=ag.asset_group_id,
                                name=ag.name,
                                ad_strength=ag.ad_strength,
                                primary_status=ag.primary_status,
                                cost_pln=round(ag.cost_micros / 1_000_000, 2),
                                conv_value=round(ag.conv_value, 2),
                            )
                            for ag in ags_by_campaign.get(c.campaign_id, [])
                        ],
                        listing_group_count=len(lgs),
                        catch_all_only=bool(lgs) and all(g.is_catch_all for g in lgs),
                    )
                )
    finally:
        await engine.dispose()

    return ShoppingHealthResponse(snapshot_date=snap_date.isoformat(), campaigns=campaigns)
