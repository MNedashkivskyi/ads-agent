"""Dashboard API endpoints — read-only time-series and aggregate views."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


# ---------------------------------------------------------------------------
# GET /api/dashboard/{user_id}/performance
# ---------------------------------------------------------------------------


@router.get("/{user_id}/performance")
async def get_performance(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    days: int = Query(default=30, ge=7, le=90, description="Look-back window in days (7–90)"),
) -> dict[str, Any]:
    """Return daily aggregated CPA/CTR/conversions for all accounts of the user.

    The caller must be authenticated as the same user_id they are querying.
    """
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's dashboard")

    since = date.today() - timedelta(days=days)
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            # Fetch account IDs belonging to this user
            from adcopilot.infrastructure.db.models import GoogleAdsAccountModel

            acct_result = await session.execute(
                select(GoogleAdsAccountModel.id, GoogleAdsAccountModel.customer_id).where(
                    GoogleAdsAccountModel.user_id == uuid.UUID(user_id)
                )
            )
            accounts = acct_result.all()
            if not accounts:
                return {"user_id": user_id, "days": days, "series": []}

            account_ids = [str(row.id) for row in accounts]

            # Daily aggregates from campaign snapshots
            from adcopilot.infrastructure.db.models import CampaignSnapshotModel

            rows = await session.execute(
                select(
                    CampaignSnapshotModel.snapshot_date,
                    text("SUM(cost_micros) AS total_cost_micros"),
                    text("SUM(clicks) AS total_clicks"),
                    text("SUM(impressions) AS total_impressions"),
                    text("SUM(conversions) AS total_conversions"),
                )
                .where(
                    CampaignSnapshotModel.account_id.in_(
                        [uuid.UUID(aid) for aid in account_ids]
                    ),
                    CampaignSnapshotModel.snapshot_date >= since,
                )
                .group_by(CampaignSnapshotModel.snapshot_date)
                .order_by(CampaignSnapshotModel.snapshot_date)
            )
            series = []
            for row in rows:
                cost = row.total_cost_micros or 0
                conv = float(row.total_conversions or 0)
                clicks = row.total_clicks or 0
                impressions = row.total_impressions or 0
                cpa_micros = int(cost / conv) if conv > 0 else 0
                ctr = clicks / impressions if impressions > 0 else 0.0
                series.append(
                    {
                        "date": str(row.snapshot_date),
                        "cost_micros": cost,
                        "clicks": clicks,
                        "impressions": impressions,
                        "conversions": conv,
                        "cpa_micros": cpa_micros,
                        "ctr": round(ctr, 6),
                    }
                )
            return {"user_id": user_id, "days": days, "series": series}
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# GET /api/dashboard/{user_id}/recommendations/impact
# ---------------------------------------------------------------------------


@router.get("/{user_id}/recommendations/impact")
async def get_recommendations_impact(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Return executed recommendations with before/after performance comparisons."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's dashboard")

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from adcopilot.infrastructure.db.models import (
                GoogleAdsAccountModel,
                PerformanceComparisonModel,
                RecommendationModel,
            )

            acct_result = await session.execute(
                select(GoogleAdsAccountModel.id).where(
                    GoogleAdsAccountModel.user_id == uuid.UUID(user_id)
                )
            )
            account_ids = [row.id for row in acct_result.all()]
            if not account_ids:
                return {"user_id": user_id, "items": []}

            rec_result = await session.execute(
                select(RecommendationModel)
                .where(
                    RecommendationModel.account_id.in_(account_ids),
                    RecommendationModel.status == "EXECUTED",
                )
                .order_by(RecommendationModel.updated_at.desc())
                .limit(50)
            )
            recs = rec_result.scalars().all()

            rec_ids = [r.id for r in recs]
            cmp_result = await session.execute(
                select(PerformanceComparisonModel).where(
                    PerformanceComparisonModel.recommendation_id.in_(rec_ids)
                )
            )
            comparisons = {c.recommendation_id: c for c in cmp_result.scalars().all()}

            items = []
            for rec in recs:
                cmp = comparisons.get(rec.id)
                items.append(
                    {
                        "recommendation_id": str(rec.id),
                        "kind": rec.kind,
                        "severity": rec.severity,
                        "estimated_monthly_savings_micros": rec.estimated_monthly_savings_micros,
                        "executed_at": rec.updated_at.isoformat() if rec.updated_at else None,
                        "comparison": {
                            "delta_cpa_pct": cmp.delta_cpa_pct,
                            "delta_conversions_pct": cmp.delta_conversions_pct,
                            "delta_ctr_pct": cmp.delta_ctr_pct,
                            "verdict": cmp.verdict,
                            "comparison_window_days": cmp.comparison_window_days,
                            "compared_at": cmp.compared_at.isoformat(),
                        }
                        if cmp
                        else None,
                    }
                )
            return {"user_id": user_id, "items": items}
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# GET /api/dashboard/{user_id}/campaigns/structure
# ---------------------------------------------------------------------------


@router.get("/{user_id}/campaigns/structure")
async def get_campaigns_structure(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    snapshot_date: date | None = Query(default=None, description="ISO date, defaults to today"),  # noqa: B008
) -> dict[str, Any]:
    """Return campaign → ad group → keyword tree with current status and key metrics."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's dashboard")

    ref_date = snapshot_date or date.today()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from adcopilot.infrastructure.db.models import (
                AdGroupSnapshotModel,
                CampaignSnapshotModel,
                GoogleAdsAccountModel,
                KeywordSnapshotModel,
            )

            acct_result = await session.execute(
                select(GoogleAdsAccountModel.id, GoogleAdsAccountModel.customer_id).where(
                    GoogleAdsAccountModel.user_id == uuid.UUID(user_id)
                )
            )
            accounts = {str(row.id): row.customer_id for row in acct_result.all()}
            if not accounts:
                return {"user_id": user_id, "snapshot_date": str(ref_date), "campaigns": []}

            account_uuids = [uuid.UUID(aid) for aid in accounts]

            camp_result = await session.execute(
                select(CampaignSnapshotModel).where(
                    CampaignSnapshotModel.account_id.in_(account_uuids),
                    CampaignSnapshotModel.snapshot_date == ref_date,
                )
            )
            campaigns = camp_result.scalars().all()

            ag_result = await session.execute(
                select(AdGroupSnapshotModel).where(
                    AdGroupSnapshotModel.account_id.in_(account_uuids),
                    AdGroupSnapshotModel.snapshot_date == ref_date,
                )
            )
            ad_groups_by_campaign: dict[int, list[Any]] = {}
            for ag in ag_result.scalars().all():
                ad_groups_by_campaign.setdefault(ag.campaign_id, []).append(ag)

            kw_result = await session.execute(
                select(KeywordSnapshotModel).where(
                    KeywordSnapshotModel.account_id.in_(account_uuids),
                    KeywordSnapshotModel.snapshot_date == ref_date,
                )
            )
            kws_by_ag: dict[int, list[Any]] = {}
            for kw in kw_result.scalars().all():
                kws_by_ag.setdefault(kw.ad_group_id, []).append(kw)

            campaign_nodes = []
            for camp in campaigns:
                ag_nodes = []
                for ag in ad_groups_by_campaign.get(camp.campaign_id, []):
                    kw_nodes = [
                        {
                            "criterion_id": kw.criterion_id,
                            "text": kw.text,
                            "match_type": kw.match_type,
                            "status": kw.status,
                            "clicks": kw.clicks,
                            "impressions": kw.impressions,
                            "cost_micros": kw.cost_micros,
                            "conversions": kw.conversions,
                            "quality_score": kw.quality_score,
                        }
                        for kw in kws_by_ag.get(ag.ad_group_id, [])
                    ]
                    ag_nodes.append(
                        {
                            "ad_group_id": ag.ad_group_id,
                            "name": ag.name,
                            "status": ag.status,
                            "clicks": ag.clicks,
                            "impressions": ag.impressions,
                            "cost_micros": ag.cost_micros,
                            "conversions": ag.conversions,
                            "keywords": kw_nodes,
                        }
                    )
                campaign_nodes.append(
                    {
                        "campaign_id": camp.campaign_id,
                        "name": camp.name,
                        "status": camp.status,
                        "clicks": camp.clicks,
                        "impressions": camp.impressions,
                        "cost_micros": camp.cost_micros,
                        "conversions": camp.conversions,
                        "ad_groups": ag_nodes,
                    }
                )
            return {
                "user_id": user_id,
                "snapshot_date": str(ref_date),
                "campaigns": campaign_nodes,
            }
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# GET /api/dashboard/{user_id}/benchmarks
# ---------------------------------------------------------------------------


@router.get("/{user_id}/benchmarks")
async def get_benchmarks(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Return account CPA/CTR vs. vertical benchmark median/p75."""
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Cannot access another user's dashboard")

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            from adcopilot.infrastructure.db.models import (
                GoogleAdsAccountModel,
                VerticalBenchmarkSnapshotModel,
            )

            acct_result = await session.execute(
                select(GoogleAdsAccountModel).where(
                    GoogleAdsAccountModel.user_id == uuid.UUID(user_id)
                )
            )
            accounts = acct_result.scalars().all()
            if not accounts:
                return {"user_id": user_id, "benchmarks": []}

            from adcopilot.domain.polish_market.city_tiers import classify_city

            items = []
            for account in accounts:
                vertical = account.vertical or "generic"
                city_tier = classify_city(getattr(account, "city", "") or "")

                bench_result = await session.execute(
                    select(VerticalBenchmarkSnapshotModel)
                    .where(
                        VerticalBenchmarkSnapshotModel.vertical == vertical,
                        VerticalBenchmarkSnapshotModel.city_tier == city_tier,
                    )
                    .order_by(VerticalBenchmarkSnapshotModel.snapshot_week.desc())
                    .limit(1)
                )
                bench = bench_result.scalar_one_or_none()

                items.append(
                    {
                        "account_id": str(account.id),
                        "customer_id": account.customer_id,
                        "vertical": vertical,
                        "city_tier": city_tier,
                        "benchmark": {
                            "snapshot_week": str(bench.snapshot_week),
                            "account_count": bench.account_count,
                            "median_cpa_micros": bench.median_cpa_micros,
                            "p75_cpa_micros": bench.p75_cpa_micros,
                            "avg_ctr": bench.avg_ctr,
                        }
                        if bench
                        else None,
                    }
                )
            return {"user_id": user_id, "benchmarks": items}
    finally:
        await engine.dispose()
