"""Use case: forecast seasonal bid opportunities for the next 30 days."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.application.ports.llm import LLMClient
from adcopilot.application.ports.prompt_version_repository import PromptVersionRepository
from adcopilot.infrastructure.db.models import CampaignSnapshotModel

logger = structlog.get_logger(__name__)

_PROMPT_KEY = "seasonality_v1"
_SYSTEM = (
    "Jesteś ekspertem Google Ads specjalizującym się w sezonowości rynku polskiego. "
    "Odpowiadaj wyłącznie po polsku. Podawaj konkretne daty, kwoty i działania."
)
_FALLBACK_PROMPT = (
    "Napisz rekomendację sezonową w języku polskim dla konta Google Ads na podstawie "
    "poniższych danych. Wskaż konkretne daty, kwoty budżetu i działania do podjęcia.\n\n"
    "Dane sezonowe:\n{seasonal_data}"
)

# Polish market vertical seasonal multipliers (month number → multiplier)
_MONTHLY_MULTIPLIERS: dict[int, float] = {
    1: 0.8,   # January — post-holiday slump
    2: 0.9,   # February
    3: 1.1,   # March — spring
    4: 1.1,   # April — spring
    5: 1.0,   # May
    6: 1.0,   # June
    7: 1.0,   # July
    8: 1.0,   # August
    9: 1.1,   # September — back to school
    10: 1.0,  # October
    11: 1.3,  # November — Black Friday
    12: 1.4,  # December — holiday shopping
}

_MONTH_NAMES_PL: dict[int, str] = {
    1: "Styczeń",
    2: "Luty",
    3: "Marzec",
    4: "Kwiecień",
    5: "Maj",
    6: "Czerwiec",
    7: "Lipiec",
    8: "Sierpień",
    9: "Wrzesień",
    10: "Październik",
    11: "Listopad",
    12: "Grudzień",
}


def _month_key(d: date) -> str:
    return d.strftime("%Y-%m")


async def forecast_seasonality(
    account_id: str,
    session: AsyncSession,
    llm: LLMClient,
    prompt_repo: PromptVersionRepository,
) -> dict:
    """Pull 12 months of history, apply seasonal multipliers, forecast next 30 days."""
    log = logger.bind(account_id=account_id)
    log.info("forecast_seasonality.start")

    acct_uuid = uuid.UUID(account_id)
    today = date.today()
    cutoff = today - timedelta(days=365)

    # -------------------------------------------------------------------------
    # 1. Pull monthly aggregated performance from CampaignSnapshotModel
    # -------------------------------------------------------------------------
    stmt = (
        select(
            func.to_char(CampaignSnapshotModel.snapshot_date, "YYYY-MM").label("month"),
            func.sum(CampaignSnapshotModel.cost_micros).label("spend_micros"),
            func.sum(CampaignSnapshotModel.clicks).label("clicks"),
            func.sum(CampaignSnapshotModel.conversions).label("conversions"),
            func.sum(CampaignSnapshotModel.impressions).label("impressions"),
        )
        .where(
            CampaignSnapshotModel.account_id == acct_uuid,
            CampaignSnapshotModel.snapshot_date >= cutoff,
        )
        .group_by(func.to_char(CampaignSnapshotModel.snapshot_date, "YYYY-MM"))
        .order_by(func.to_char(CampaignSnapshotModel.snapshot_date, "YYYY-MM"))
    )
    rows = (await session.execute(stmt)).all()

    monthly_history: list[dict] = []
    for r in rows:
        month_str: str = r.month
        clicks = int(r.clicks or 0)
        impressions = int(r.impressions or 0)
        ctr = clicks / impressions if impressions > 0 else 0.0
        # derive month number from "YYYY-MM"
        month_num = int(month_str.split("-")[1])
        multiplier = _MONTHLY_MULTIPLIERS.get(month_num, 1.0)
        monthly_history.append(
            {
                "month": month_str,
                "spend_micros": int(r.spend_micros or 0),
                "clicks": clicks,
                "conversions": float(r.conversions or 0.0),
                "ctr": round(ctr, 4),
                "multiplier": multiplier,
            }
        )

    # -------------------------------------------------------------------------
    # 2. Build upcoming 30-day events
    # -------------------------------------------------------------------------
    upcoming_events: list[dict] = []
    for day_offset in range(30):
        d = today + timedelta(days=day_offset)
        current_multiplier = _MONTHLY_MULTIPLIERS.get(d.month, 1.0)

        # Determine next month
        next_month_num = 1 if d.month == 12 else d.month + 1
        next_multiplier = _MONTHLY_MULTIPLIERS.get(next_month_num, 1.0)

        event_type: str | None = None
        event_name_pl: str | None = None
        recommended_budget_change_pct: float = 0.0
        confidence: float = 0.0

        if current_multiplier < 1.0 and next_multiplier > 1.1:
            # 14-day window before a peak
            days_until_month_end = (
                date(d.year if d.month < 12 else d.year + 1, next_month_num, 1) - d
            ).days
            if days_until_month_end <= 14:
                event_type = "peak"
                event_name_pl = (
                    f"Nadchodzący szczyt sezonowy — {_MONTH_NAMES_PL[next_month_num]}"
                )
                recommended_budget_change_pct = round((next_multiplier - 1.0) * 100, 1)
                confidence = 0.75

        if current_multiplier > 1.0 and next_multiplier < 0.9:
            days_until_month_end = (
                date(d.year if d.month < 12 else d.year + 1, next_month_num, 1) - d
            ).days
            if days_until_month_end <= 14:
                event_type = "trough"
                event_name_pl = (
                    f"Nadchodzące spowolnienie sezonowe — {_MONTH_NAMES_PL[next_month_num]}"
                )
                recommended_budget_change_pct = round((next_multiplier - 1.0) * 100, 1)
                confidence = 0.70

        if event_type is not None:
            upcoming_events.append(
                {
                    "date": d.isoformat(),
                    "event_name_pl": event_name_pl,
                    "type": event_type,
                    "recommended_budget_change_pct": recommended_budget_change_pct,
                    "confidence": confidence,
                }
            )

    # Deduplicate — keep first occurrence per event_name_pl
    seen: set[str] = set()
    deduped_events: list[dict] = []
    for ev in upcoming_events:
        key = ev["event_name_pl"]
        if key not in seen:
            seen.add(key)
            deduped_events.append(ev)
    upcoming_events = deduped_events

    # -------------------------------------------------------------------------
    # 3. Call Claude Haiku for Polish narrative recommendation
    # -------------------------------------------------------------------------
    seasonal_data = {
        "account_id": account_id,
        "monthly_history": monthly_history[-6:],  # last 6 months for conciseness
        "multipliers": {str(k): v for k, v in _MONTHLY_MULTIPLIERS.items()},
        "upcoming_events": upcoming_events,
        "current_month": today.strftime("%Y-%m"),
    }

    try:
        prompt_template = await prompt_repo.get_latest(_PROMPT_KEY)
        prompt_text = (
            prompt_template.content.format(
                seasonal_data=json.dumps(seasonal_data, ensure_ascii=False, indent=2)
            )
            if prompt_template
            else _FALLBACK_PROMPT.format(
                seasonal_data=json.dumps(seasonal_data, ensure_ascii=False, indent=2)
            )
        )
    except Exception:
        prompt_text = _FALLBACK_PROMPT.format(
            seasonal_data=json.dumps(seasonal_data, ensure_ascii=False, indent=2)
        )

    if monthly_history or upcoming_events:
        recommendations_pl = await llm.complete(
            system=_SYSTEM,
            user=prompt_text,
            max_tokens=600,
            temperature=0.4,
        )
    else:
        recommendations_pl = (
            "Brak historycznych danych kampanii. Upewnij się, że dane snapshots są "
            "regularnie synchronizowane, aby umożliwić analizę sezonowości."
        )

    generated_at = datetime.now(tz=UTC).isoformat()
    log.info(
        "forecast_seasonality.done",
        months=len(monthly_history),
        events=len(upcoming_events),
    )

    return {
        "account_id": account_id,
        "monthly_history": monthly_history,
        "multipliers": {str(k): v for k, v in _MONTHLY_MULTIPLIERS.items()},
        "upcoming_events": upcoming_events,
        "recommendations_pl": recommendations_pl.strip() if isinstance(recommendations_pl, str) else recommendations_pl,
        "generated_at": generated_at,
    }
