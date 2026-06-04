"""Use case: evaluate a QS improvement plan after its measurement window."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.config import get_settings
from adcopilot.domain.qs_improvement_plan import QSImprovementPlan, QSMetrics, QSPlanStatus
from adcopilot.infrastructure.db.repositories.qs_improvement_plan_repository import (
    QSImprovementPlanRepository,
)

logger = structlog.get_logger(__name__)

_EVAL_PROMPT = """Jesteś ekspertem Google Ads. Ocen wyniki planu poprawy Quality Score:

Konto: {account_id}
QS przed: {qs_before:.1f}
QS po: {qs_after:.1f}
Zmiana QS: {qs_delta:+.1f}
Status: {status}

Napisz zwięzłe (3-5 zdań) podsumowanie wyników po polsku. Jeśli wyniki są pozytywne, podkreśl oszczędności. Jeśli negatywne, zasugeruj kolejne kroki."""


async def evaluate_qs_improvement_plan(
    plan_id: str,
    session: AsyncSession,
) -> QSImprovementPlan:
    repo = QSImprovementPlanRepository(session)
    plan = await repo.get(plan_id)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found")

    if plan.status != QSPlanStatus.MEASURING:
        raise ValueError(f"Plan {plan_id} is not in MEASURING status")

    now = datetime.now(UTC)
    if plan.measurement_ends_at and plan.measurement_ends_at > now:
        raise ValueError(f"Plan {plan_id} measurement window has not ended yet")

    current_metrics = await _fetch_current_metrics(plan, session)
    baseline_qs = plan.baseline_metrics.avg_qs if plan.baseline_metrics else None
    current_qs = current_metrics.avg_qs

    qs_improved = (
        baseline_qs is not None and current_qs is not None and (current_qs - baseline_qs) >= 1.0
    )
    new_status = QSPlanStatus.COMPLETED if qs_improved else QSPlanStatus.FAILED

    summary = await _generate_evaluation_summary(plan, baseline_qs, current_qs, new_status)

    updated_plan = QSImprovementPlan(
        id=plan.id,
        account_id=plan.account_id,
        keyword_criterion_ids=plan.keyword_criterion_ids,
        target_ad_group_resource_name=plan.target_ad_group_resource_name,
        current_avg_qs=current_qs,
        target_qs=plan.target_qs,
        bottleneck_component=plan.bottleneck_component,
        prescribed_actions=plan.prescribed_actions,
        status=new_status,
        baseline_metrics=plan.baseline_metrics,
        current_metrics=current_metrics,
        evaluation_summary_pl=summary,
        created_at=plan.created_at,
        started_at=plan.started_at,
        measurement_ends_at=plan.measurement_ends_at,
        completed_at=now,
    )

    await repo.save(updated_plan)
    await _send_notification(updated_plan, session)

    logger.info(
        "qs_plan_evaluated",
        plan_id=plan_id,
        status=new_status.value,
        qs_before=baseline_qs,
        qs_after=current_qs,
    )
    return updated_plan


async def _fetch_current_metrics(
    plan: QSImprovementPlan,
    session: AsyncSession,
) -> QSMetrics:
    from sqlalchemy import select, text

    from adcopilot.infrastructure.db.models import KeywordSnapshotModel

    if not plan.keyword_criterion_ids:
        return QSMetrics(avg_qs=None, avg_cpc_micros=None, avg_ctr=None)

    result = await session.execute(
        select(KeywordSnapshotModel)
        .where(KeywordSnapshotModel.account_id == plan.account_id)
        .where(KeywordSnapshotModel.criterion_id.in_(plan.keyword_criterion_ids))
        .order_by(text("snapshot_date DESC"))
        .limit(len(plan.keyword_criterion_ids) * 3)
    )
    rows = list(result.scalars().all())

    # Keep only most-recent snapshot per criterion
    seen: set[int] = set()
    latest: list = []
    for r in rows:
        if r.criterion_id not in seen:
            seen.add(r.criterion_id)
            latest.append(r)

    scores = [r.quality_score for r in latest if r.quality_score is not None]
    avg_qs = sum(scores) / len(scores) if scores else None
    return QSMetrics(avg_qs=avg_qs, avg_cpc_micros=None, avg_ctr=None)


async def _generate_evaluation_summary(
    plan: QSImprovementPlan,
    qs_before: float | None,
    qs_after: float | None,
    status: QSPlanStatus,
) -> str | None:
    try:
        import anthropic

        settings = get_settings()
        before = qs_before or 0.0
        after = qs_after or 0.0
        status_pl = "sukces" if status == QSPlanStatus.COMPLETED else "brak poprawy"
        prompt = _EVAL_PROMPT.format(
            account_id=plan.account_id,
            qs_before=before,
            qs_after=after,
            qs_delta=after - before,
            status=status_pl,
        )
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        msg = await client.messages.create(
            model=settings.LLM_MODEL_DEFAULT,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text if msg.content else None
    except Exception as exc:
        logger.warning("qs_eval_summary_failed", error=str(exc))
        return None


async def _send_notification(plan: QSImprovementPlan, session: AsyncSession) -> None:
    try:
        import uuid
        from datetime import UTC, datetime

        from adcopilot.domain.notification import Notification, NotificationId, NotificationType
        from adcopilot.infrastructure.db.repositories.notification_repository import (
            NotificationRepository,
        )

        repo = NotificationRepository(session)
        status_pl = "zakończony sukcesem" if plan.status == QSPlanStatus.COMPLETED else "nieudany"
        body = plan.evaluation_summary_pl or f"Plan QS {status_pl}."
        notif = Notification(
            id=NotificationId(str(uuid.uuid4())),
            user_id=plan.account_id,
            notification_type=NotificationType.EXECUTION_RESULT,
            title=f"Plan poprawy QS — {status_pl}",
            body=body,
            metadata={"plan_id": plan.id, "status": plan.status.value},
            read_at=None,
            created_at=datetime.now(UTC),
        )
        await repo.save(notif)
    except Exception as exc:
        logger.warning("qs_plan_notification_failed", plan_id=plan.id, error=str(exc))
