"""Use case: analyze audience strategy and generate Polish recommendations."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.infrastructure.db.models import AudiencePerformanceSnapshotModel

logger = structlog.get_logger(__name__)

_LOOKBACK_DAYS = 30
_PROMPT_KEY = "audience_strategy_v1"
_SYSTEM = (
    "Jesteś ekspertem Google Ads ds. strategii audience dla polskich firm MŚP. "
    "Odpowiadaj wyłącznie po polsku. Bądź konkretny i cytuj liczby."
)
_FALLBACK_PROMPT = (
    "Przeanalizuj poniższe dane o wydajności grup odbiorców Google Ads i napisz "
    "3–5 konkretnych rekomendacji strategicznych w języku polskim.\n\nDane:\n{audience_context}"
)


async def analyze_audience_strategy(
    account_id: str,
    session: AsyncSession,
    llm: LLMClient,
    prompt_repo: PromptVersionRepository,
) -> dict:
    """Analyze audience performance and return strategic recommendations in Polish."""
    log = logger.bind(account_id=account_id)
    log.info("analyze_audience_strategy.start")

    acct_uuid = uuid.UUID(account_id)
    cutoff = (datetime.now(tz=UTC) - timedelta(days=_LOOKBACK_DAYS)).date()

    # -------------------------------------------------------------------------
    # 1. Aggregate audience metrics over the lookback window
    # -------------------------------------------------------------------------
    stmt = (
        select(
            AudiencePerformanceSnapshotModel.criterion_id,
            AudiencePerformanceSnapshotModel.campaign_id,
            AudiencePerformanceSnapshotModel.ad_group_id,
            func.sum(AudiencePerformanceSnapshotModel.clicks).label("clicks"),
            func.sum(AudiencePerformanceSnapshotModel.cost_micros).label("cost_micros"),
            func.sum(AudiencePerformanceSnapshotModel.conversions).label("conversions"),
            func.sum(AudiencePerformanceSnapshotModel.impressions).label("impressions"),
        )
        .where(
            AudiencePerformanceSnapshotModel.account_id == acct_uuid,
            AudiencePerformanceSnapshotModel.snapshot_date >= cutoff,
        )
        .group_by(
            AudiencePerformanceSnapshotModel.criterion_id,
            AudiencePerformanceSnapshotModel.campaign_id,
            AudiencePerformanceSnapshotModel.ad_group_id,
        )
    )
    rows = (await session.execute(stmt)).all()

    audiences: list[dict] = []
    for r in rows:
        clicks = int(r.clicks or 0)
        conversions = float(r.conversions or 0.0)
        cost_micros = int(r.cost_micros or 0)
        conv_rate = conversions / clicks if clicks > 0 else 0.0
        cpa = (cost_micros / 1_000_000) / conversions if conversions > 0 else None
        audiences.append(
            {
                "criterion_id": r.criterion_id,
                "campaign_id": r.campaign_id,
                "ad_group_id": r.ad_group_id,
                "clicks": clicks,
                "conversions": conversions,
                "cost_micros": cost_micros,
                "conv_rate": conv_rate,
                "cpa": cpa,
            }
        )

    # -------------------------------------------------------------------------
    # 2. Identify top performers and underperformers
    # -------------------------------------------------------------------------
    top_performers: list[dict] = []
    underperformers: list[dict] = []

    if audiences:
        avg_conv_rate = sum(a["conv_rate"] for a in audiences) / len(audiences)
        cpas = [a["cpa"] for a in audiences if a["cpa"] is not None]
        avg_cpa = sum(cpas) / len(cpas) if cpas else None

        for a in audiences:
            if a["conv_rate"] > avg_conv_rate * 1.30:
                top_performers.append(
                    {
                        "criterion_id": a["criterion_id"],
                        "campaign_id": a["campaign_id"],
                        "conv_rate": round(a["conv_rate"], 4),
                        "conversions": a["conversions"],
                        "cost_micros": a["cost_micros"],
                    }
                )
            if avg_cpa is not None and a["cpa"] is not None and a["cpa"] > avg_cpa * 2.0:
                underperformers.append(
                    {
                        "criterion_id": a["criterion_id"],
                        "campaign_id": a["campaign_id"],
                        "cpa": round(a["cpa"], 2),
                        "conversions": a["conversions"],
                        "cost_micros": a["cost_micros"],
                    }
                )

    # -------------------------------------------------------------------------
    # 3. Build context for LLM
    # -------------------------------------------------------------------------
    audience_context = {
        "account_id": account_id,
        "total_audiences_analyzed": len(audiences),
        "top_performers_count": len(top_performers),
        "underperformers_count": len(underperformers),
        "top_performers": top_performers[:10],
        "underperformers": underperformers[:10],
    }

    # -------------------------------------------------------------------------
    # 4. Call Claude Haiku for Polish recommendations
    # -------------------------------------------------------------------------
    try:
        prompt_template = await prompt_repo.get_latest(_PROMPT_KEY)
        prompt_text = (
            prompt_template.content.format(
                audience_context=json.dumps(audience_context, ensure_ascii=False, indent=2)
            )
            if prompt_template
            else _FALLBACK_PROMPT.format(
                audience_context=json.dumps(audience_context, ensure_ascii=False, indent=2)
            )
        )
    except Exception:
        prompt_text = _FALLBACK_PROMPT.format(
            audience_context=json.dumps(audience_context, ensure_ascii=False, indent=2)
        )

    if audiences:
        recommendations_pl = await llm.complete(
            system=_SYSTEM,
            user=prompt_text,
            max_tokens=600,
            temperature=0.4,
        )
    else:
        recommendations_pl = (
            "Brak danych o grupach odbiorców w analizowanym okresie. "
            "Upewnij się, że kampanie mają przypisane listy remarketingowe lub segmenty odbiorców, "
            "a snapshot danych jest aktualny."
        )

    analyzed_at = datetime.now(tz=UTC).isoformat()
    log.info(
        "analyze_audience_strategy.done",
        top_performers=len(top_performers),
        underperformers=len(underperformers),
    )

    return {
        "account_id": account_id,
        "top_performers": top_performers,
        "underperformers": underperformers,
        "recommendations_pl": recommendations_pl.strip(),
        "analyzed_at": analyzed_at,
    }
