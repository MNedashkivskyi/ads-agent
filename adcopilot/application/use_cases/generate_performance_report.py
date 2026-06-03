"""Use case: generate a structured performance report for a period."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.application.use_cases.get_latest_prompt import get_latest_prompt
from adcopilot.infrastructure.db.models import (
    QSImprovementPlanModel,
    RecommendationModel,
)

logger = structlog.get_logger(__name__)

_PROMPT_KEY = "performance_report_v1"
_SYSTEM = (
    "Jestes analitykiem Google Ads tworzacym miesieczne raporty dla polskich firm MSP."
    " Odpowiadaj wylacznie po polsku. Badz konkretny i cytuj liczby."
)


async def generate_performance_report(
    user_id: str,
    account_id: str,
    period_start: date,
    period_end: date,
    session: AsyncSession,
    llm: LLMClient,
    prompt_repo: PromptVersionRepository,
) -> dict:
    """Generate a structured performance report for a given period."""
    import uuid as _uuid

    account_uuid = _uuid.UUID(account_id)
    period_length = (period_end - period_start).days

    # -----------------------------------------------------------------------
    # Current period aggregates from CampaignSnapshotModel (has spend/clicks)
    # -----------------------------------------------------------------------
    from adcopilot.infrastructure.db.models import CampaignSnapshotModel

    cur_stmt = select(
        func.sum(CampaignSnapshotModel.cost_micros).label("spend_micros"),
        func.sum(CampaignSnapshotModel.clicks).label("clicks"),
        func.sum(CampaignSnapshotModel.impressions).label("impressions"),
        func.sum(CampaignSnapshotModel.conversions).label("conversions"),
    ).where(
        CampaignSnapshotModel.account_id == account_uuid,
        CampaignSnapshotModel.snapshot_date >= period_start,
        CampaignSnapshotModel.snapshot_date <= period_end,
    )
    cur_result = (await session.execute(cur_stmt)).one()

    spend_micros: int = cur_result.spend_micros or 0
    clicks: int = cur_result.clicks or 0
    impressions: int = cur_result.impressions or 0
    conversions: float = cur_result.conversions or 0.0

    spend_pln = spend_micros / 1_000_000
    ctr = (clicks / impressions) if impressions > 0 else 0.0
    cpa = (spend_pln / conversions) if conversions > 0 else None

    metrics = {
        "spend_pln": round(spend_pln, 2),
        "clicks": int(clicks),
        "impressions": int(impressions),
        "conversions": round(conversions, 2),
        "ctr": round(ctr * 100, 4),  # percent
        "cpa": round(cpa, 2) if cpa is not None else None,
        "roas": None,
    }

    # -----------------------------------------------------------------------
    # Previous period comparison
    # -----------------------------------------------------------------------
    prev_end = period_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=period_length)

    prev_stmt = select(
        func.sum(CampaignSnapshotModel.cost_micros).label("spend_micros"),
        func.sum(CampaignSnapshotModel.clicks).label("clicks"),
        func.sum(CampaignSnapshotModel.impressions).label("impressions"),
        func.sum(CampaignSnapshotModel.conversions).label("conversions"),
    ).where(
        CampaignSnapshotModel.account_id == account_uuid,
        CampaignSnapshotModel.snapshot_date >= prev_start,
        CampaignSnapshotModel.snapshot_date <= prev_end,
    )
    prev_result = (await session.execute(prev_stmt)).one()

    prev_spend_micros: int = prev_result.spend_micros or 0
    prev_clicks: int = prev_result.clicks or 0
    prev_impressions: int = prev_result.impressions or 0
    prev_conversions: float = prev_result.conversions or 0.0
    prev_spend_pln = prev_spend_micros / 1_000_000
    prev_ctr = (prev_clicks / prev_impressions) if prev_impressions > 0 else 0.0
    prev_cpa = (prev_spend_pln / prev_conversions) if prev_conversions > 0 else None

    comparison = {
        "period_start": prev_start.isoformat(),
        "period_end": prev_end.isoformat(),
        "spend_pln": round(prev_spend_pln, 2),
        "clicks": int(prev_clicks),
        "impressions": int(prev_impressions),
        "conversions": round(prev_conversions, 2),
        "ctr": round(prev_ctr * 100, 4),
        "cpa": round(prev_cpa, 2) if prev_cpa is not None else None,
        # Honesty layer: a period-over-period comparison is observational, not causal —
        # seasonality and auction dynamics move these numbers on their own.
        "evidence_grade": "OBSERVATIONAL",
        "evidence_note": (
            "Porównanie okres do okresu ma charakter obserwacyjny — pokazuje zmianę, "
            "ale nie dowodzi, że wynika ona z wprowadzonych zmian (wpływ sezonowości i aukcji). "
            "Aby zmierzyć rzeczywisty wpływ konkretnej zmiany, uruchom eksperyment."
        ),
    }

    # -----------------------------------------------------------------------
    # Top 5 executed recommendations in this period
    # -----------------------------------------------------------------------
    rec_stmt = (
        select(RecommendationModel)
        .where(
            RecommendationModel.account_id == account_uuid,
            RecommendationModel.status == "APPROVED",
            RecommendationModel.updated_at >= datetime.combine(period_start, datetime.min.time()),
            RecommendationModel.updated_at <= datetime.combine(period_end, datetime.max.time()),
        )
        .order_by(RecommendationModel.estimated_monthly_savings_micros.desc())
        .limit(5)
    )
    rec_rows = (await session.execute(rec_stmt)).scalars().all()
    top_recommendations = [
        {
            "kind": r.kind,
            "estimated_savings_pln": round(r.estimated_monthly_savings_micros / 1_000_000, 2),
        }
        for r in rec_rows
    ]

    # -----------------------------------------------------------------------
    # QS improvement plan summary for this account
    # -----------------------------------------------------------------------
    qs_stmt = (
        select(
            QSImprovementPlanModel.status,
            func.count(QSImprovementPlanModel.id).label("count"),
        )
        .where(
            QSImprovementPlanModel.account_id == account_uuid,
        )
        .group_by(QSImprovementPlanModel.status)
    )

    qs_rows = (await session.execute(qs_stmt)).all()
    qs_plan_summary = {row.status: row.count for row in qs_rows}

    # -----------------------------------------------------------------------
    # Build context and call LLM
    # -----------------------------------------------------------------------
    account_context = {
        "account_id": account_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "metrics": metrics,
        "comparison": comparison,
        "top_recommendations": top_recommendations,
        "qs_plan_summary": qs_plan_summary,
    }

    prompt_template = await get_latest_prompt(prompt_repo, _PROMPT_KEY)
    user_msg = prompt_template.format(
        account_context=json.dumps(account_context, ensure_ascii=False, indent=2)
    )

    summary_pl = await llm.complete(
        system=_SYSTEM,
        user=user_msg,
        max_tokens=800,
        temperature=0.4,
    )
    summary_pl = summary_pl.strip()

    logger.info(
        "performance_report.generated",
        user_id=user_id,
        account_id=account_id,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )

    return {
        "user_id": user_id,
        "account_id": account_id,
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "metrics": metrics,
        "comparison": comparison,
        "top_recommendations": top_recommendations,
        "qs_plan_summary": qs_plan_summary,
        "summary_pl": summary_pl,
        "generated_at": datetime.now(UTC).isoformat(),
    }
