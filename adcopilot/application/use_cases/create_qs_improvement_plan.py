"""Use case: create a coordinated QS improvement plan for low-QS keywords."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.config import get_settings
from adcopilot.domain.qs_improvement_plan import (
    QSAction,
    QSActionStatus,
    QSActionType,
    QSBottleneckComponent,
    QSImprovementPlan,
    QSImprovementPlanId,
    QSMetrics,
    QSPlanStatus,
)
from adcopilot.infrastructure.db.models import KeywordSnapshotModel

logger = structlog.get_logger(__name__)

_DIAGNOSIS_PROMPT = """Jesteś ekspertem Google Ads. Przeanalizuj plan poprawy Quality Score:

Konto: {account_id}
Słowa kluczowe z niskim QS: {keyword_count}
Średni QS: {avg_qs:.1f}
Wąskie gardło: {bottleneck}
Zaplanowane działania: {actions}

Napisz krótką (3-5 zdań) diagnozę po polsku i wyjaśnij, dlaczego te działania powinny poprawić QS."""


async def create_qs_improvement_plan(
    account_id: str,
    session: AsyncSession,
    keyword_criterion_ids: list[int] | None = None,
) -> QSImprovementPlan:
    """Create a QS improvement plan, auto-selecting low-QS keywords if none provided."""
    if keyword_criterion_ids:
        rows = await _fetch_specific_keywords(account_id, keyword_criterion_ids, session)
    else:
        rows = await _fetch_low_qs_keywords(account_id, session)

    if not rows:
        raise ValueError(f"No eligible keywords found for account {account_id}")

    avg_qs = _compute_avg_qs(rows)
    bottleneck = _identify_bottleneck(rows)
    actions = _prescribe_actions(bottleneck)
    ad_group = rows[0].ad_group_id if rows else None
    ad_group_resource = f"customers/{account_id}/adGroups/{ad_group}" if ad_group else None

    summary = await _generate_summary(account_id, rows, bottleneck, actions)

    plan = QSImprovementPlan(
        id=QSImprovementPlanId(str(uuid.uuid4())),
        account_id=account_id,
        keyword_criterion_ids=[r.criterion_id for r in rows],
        target_ad_group_resource_name=ad_group_resource,
        current_avg_qs=avg_qs,
        target_qs=min((avg_qs or 0) + 2.0, 9.0),
        bottleneck_component=bottleneck,
        prescribed_actions=actions,
        status=QSPlanStatus.PROPOSED,
        baseline_metrics=QSMetrics(
            avg_qs=avg_qs,
            avg_cpc_micros=_compute_avg_cpc(rows),
            avg_ctr=_compute_avg_ctr(rows),
        ),
        current_metrics=None,
        evaluation_summary_pl=summary,
        created_at=datetime.now(UTC),
        started_at=None,
        measurement_ends_at=None,
        completed_at=None,
    )

    logger.info(
        "qs_improvement_plan_created",
        account_id=account_id,
        plan_id=plan.id,
        keywords=len(rows),
        bottleneck=bottleneck.value,
    )
    return plan


async def _fetch_low_qs_keywords(
    account_id: str,
    session: AsyncSession,
    min_impressions: int = 100,
    max_qs: int = 5,
    limit: int = 20,
) -> list[KeywordSnapshotModel]:
    result = await session.execute(
        select(KeywordSnapshotModel)
        .where(KeywordSnapshotModel.account_id == account_id)
        .where(KeywordSnapshotModel.quality_score.isnot(None))
        .where(KeywordSnapshotModel.quality_score <= max_qs)
        .where(KeywordSnapshotModel.impressions >= min_impressions)
        .order_by(text("snapshot_date DESC"), KeywordSnapshotModel.impressions.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _fetch_specific_keywords(
    account_id: str,
    criterion_ids: list[int],
    session: AsyncSession,
) -> list[KeywordSnapshotModel]:
    result = await session.execute(
        select(KeywordSnapshotModel)
        .where(KeywordSnapshotModel.account_id == account_id)
        .where(KeywordSnapshotModel.criterion_id.in_(criterion_ids))
        .order_by(text("snapshot_date DESC"))
    )
    return list(result.scalars().all())


def _compute_avg_qs(rows: list[KeywordSnapshotModel]) -> float | None:
    scores = [r.quality_score for r in rows if r.quality_score is not None]
    return sum(scores) / len(scores) if scores else None


def _compute_avg_cpc(rows: list[KeywordSnapshotModel]) -> int | None:
    cpcs = [r.cost_micros for r in rows if hasattr(r, "cost_micros") and r.cost_micros]
    return int(sum(cpcs) / len(cpcs)) if cpcs else None


def _compute_avg_ctr(rows: list[KeywordSnapshotModel]) -> float | None:
    ctrs = [r.ctr for r in rows if hasattr(r, "ctr") and r.ctr is not None]
    return sum(ctrs) / len(ctrs) if ctrs else None


def _identify_bottleneck(rows: list[KeywordSnapshotModel]) -> QSBottleneckComponent:
    """Pick the subscore with the most BELOW_AVERAGE ratings."""
    counts = {
        QSBottleneckComponent.AD_RELEVANCE: 0,
        QSBottleneckComponent.LANDING_PAGE_EXPERIENCE: 0,
        QSBottleneckComponent.EXPECTED_CTR: 0,
    }
    for r in rows:
        if r.ad_relevance == "BELOW_AVERAGE":
            counts[QSBottleneckComponent.AD_RELEVANCE] += 1
        if r.landing_page_experience == "BELOW_AVERAGE":
            counts[QSBottleneckComponent.LANDING_PAGE_EXPERIENCE] += 1
        if r.expected_ctr == "BELOW_AVERAGE":
            counts[QSBottleneckComponent.EXPECTED_CTR] += 1

    max_count = max(counts.values())
    if max_count == 0:
        return QSBottleneckComponent.MIXED

    winners = [k for k, v in counts.items() if v == max_count]
    if len(winners) > 1:
        return QSBottleneckComponent.MIXED
    return winners[0]


def _prescribe_actions(bottleneck: QSBottleneckComponent) -> list[QSAction]:
    if bottleneck == QSBottleneckComponent.AD_RELEVANCE:
        return [
            QSAction(
                action_type=QSActionType.REFRESH_AD_COPY,
                status=QSActionStatus.PENDING,
                recommendation_id=None,
                details_json={"reason": "ad_relevance_below_average"},
            ),
            QSAction(
                action_type=QSActionType.CREATE_EXPERIMENT,
                status=QSActionStatus.PENDING,
                recommendation_id=None,
                details_json={"depends_on": "REFRESH_AD_COPY"},
            ),
        ]
    if bottleneck == QSBottleneckComponent.LANDING_PAGE_EXPERIENCE:
        return [
            QSAction(
                action_type=QSActionType.SCORE_LANDING_PAGE,
                status=QSActionStatus.PENDING,
                recommendation_id=None,
                details_json={"reason": "landing_page_experience_below_average"},
            ),
        ]
    if bottleneck == QSBottleneckComponent.EXPECTED_CTR:
        return [
            QSAction(
                action_type=QSActionType.REFRESH_AD_COPY,
                status=QSActionStatus.PENDING,
                recommendation_id=None,
                details_json={"reason": "expected_ctr_below_average", "focus": "ctr"},
            ),
            QSAction(
                action_type=QSActionType.ADD_NEGATIVE,
                status=QSActionStatus.PENDING,
                recommendation_id=None,
                details_json={"reason": "improve_relevance_via_negatives"},
            ),
        ]
    # MIXED
    return [
        QSAction(
            action_type=QSActionType.REFRESH_AD_COPY,
            status=QSActionStatus.PENDING,
            recommendation_id=None,
            details_json={"reason": "mixed_bottleneck"},
        ),
        QSAction(
            action_type=QSActionType.SCORE_LANDING_PAGE,
            status=QSActionStatus.PENDING,
            recommendation_id=None,
            details_json={"reason": "mixed_bottleneck"},
        ),
    ]


async def _generate_summary(
    account_id: str,
    rows: list[KeywordSnapshotModel],
    bottleneck: QSBottleneckComponent,
    actions: list[QSAction],
) -> str | None:
    try:
        import anthropic

        settings = get_settings()
        bottleneck_pl = {
            QSBottleneckComponent.AD_RELEVANCE: "trafność reklamy",
            QSBottleneckComponent.LANDING_PAGE_EXPERIENCE: "jakość strony docelowej",
            QSBottleneckComponent.EXPECTED_CTR: "przewidywany CTR",
            QSBottleneckComponent.MIXED: "wiele składowych",
        }[bottleneck]
        action_names = ", ".join(a.action_type.value for a in actions)
        avg = _compute_avg_qs(rows) or 0

        prompt = _DIAGNOSIS_PROMPT.format(
            account_id=account_id,
            keyword_count=len(rows),
            avg_qs=avg,
            bottleneck=bottleneck_pl,
            actions=action_names,
        )
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.LLM_MODEL_DEFAULT,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text if msg.content else None
    except Exception as exc:
        logger.warning("qs_plan_summary_failed", error=str(exc))
        return None
