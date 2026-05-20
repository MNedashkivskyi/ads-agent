"""Use case: execute a QS improvement plan by running prescribed actions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.qs_improvement_plan import (
    QSAction,
    QSActionStatus,
    QSActionType,
    QSImprovementPlan,
    QSPlanStatus,
)
from adcopilot.infrastructure.db.repositories.qs_improvement_plan_repository import (
    QSImprovementPlanRepository,
)

logger = structlog.get_logger(__name__)

_MEASUREMENT_WINDOW_AD_DAYS = 14
_MEASUREMENT_WINDOW_LP_DAYS = 30


async def execute_qs_improvement_plan(
    plan_id: str,
    session: AsyncSession,
) -> QSImprovementPlan:
    repo = QSImprovementPlanRepository(session)
    plan = await repo.get(plan_id)
    if plan is None:
        raise ValueError(f"Plan {plan_id} not found")

    if plan.status not in (QSPlanStatus.PROPOSED, QSPlanStatus.IN_PROGRESS):
        raise ValueError(f"Plan {plan_id} is in status {plan.status.value}, cannot execute")

    updated_actions = []
    has_lp_action = False

    for action in plan.prescribed_actions:
        updated_action = await _execute_action(action, plan, session)
        updated_actions.append(updated_action)
        if action.action_type == QSActionType.SCORE_LANDING_PAGE:
            has_lp_action = True

    measurement_days = _MEASUREMENT_WINDOW_LP_DAYS if has_lp_action else _MEASUREMENT_WINDOW_AD_DAYS
    now = datetime.now(UTC)

    updated_plan = QSImprovementPlan(
        id=plan.id,
        account_id=plan.account_id,
        keyword_criterion_ids=plan.keyword_criterion_ids,
        target_ad_group_resource_name=plan.target_ad_group_resource_name,
        current_avg_qs=plan.current_avg_qs,
        target_qs=plan.target_qs,
        bottleneck_component=plan.bottleneck_component,
        prescribed_actions=updated_actions,
        status=QSPlanStatus.IN_PROGRESS,
        baseline_metrics=plan.baseline_metrics,
        current_metrics=plan.current_metrics,
        evaluation_summary_pl=plan.evaluation_summary_pl,
        created_at=plan.created_at,
        started_at=plan.started_at or now,
        measurement_ends_at=now + timedelta(days=measurement_days),
        completed_at=None,
    )

    await repo.save(updated_plan)
    logger.info(
        "qs_plan_execution_started",
        plan_id=plan_id,
        actions=len(updated_actions),
        measurement_ends_at=updated_plan.measurement_ends_at,
    )
    return updated_plan


async def _execute_action(
    action: QSAction,
    plan: QSImprovementPlan,
    session: AsyncSession,
) -> QSAction:
    try:
        if action.action_type == QSActionType.REFRESH_AD_COPY:
            rec_id = await _trigger_ad_copy_refresh(plan, session)
            return QSAction(
                action_type=action.action_type,
                status=QSActionStatus.IN_PROGRESS,
                recommendation_id=rec_id,
                details_json={**action.details_json, "triggered_at": datetime.now(UTC).isoformat()},
            )

        if action.action_type == QSActionType.SCORE_LANDING_PAGE:
            rec_id = await _trigger_landing_page_score(plan, session)
            return QSAction(
                action_type=action.action_type,
                status=QSActionStatus.IN_PROGRESS,
                recommendation_id=rec_id,
                details_json={**action.details_json, "triggered_at": datetime.now(UTC).isoformat()},
            )

        if action.action_type == QSActionType.CREATE_EXPERIMENT:
            # Experiment is created after ad copy is approved; mark pending for now
            return QSAction(
                action_type=action.action_type,
                status=QSActionStatus.PENDING,
                recommendation_id=None,
                details_json=action.details_json,
            )

        return QSAction(
            action_type=action.action_type,
            status=QSActionStatus.IN_PROGRESS,
            recommendation_id=action.recommendation_id,
            details_json=action.details_json,
        )

    except Exception as exc:
        logger.warning("qs_action_execution_failed", action=action.action_type.value, error=str(exc))
        return QSAction(
            action_type=action.action_type,
            status=QSActionStatus.FAILED,
            recommendation_id=action.recommendation_id,
            details_json={**action.details_json, "error": str(exc)},
        )


async def _trigger_ad_copy_refresh(
    plan: QSImprovementPlan,
    session: AsyncSession,
) -> str | None:
    try:
        from adcopilot.application.use_cases.refresh_ad_copy import refresh_ad_copy

        if not plan.target_ad_group_resource_name:
            return None
        result = await refresh_ad_copy(
            account_id=plan.account_id,
            ad_group_resource_name=plan.target_ad_group_resource_name,
            session=session,
        )
        return getattr(result, "recommendation_id", None)
    except Exception as exc:
        logger.warning("ad_copy_refresh_failed", plan_id=plan.id, error=str(exc))
        return None


async def _trigger_landing_page_score(
    plan: QSImprovementPlan,
    session: AsyncSession,
) -> str | None:
    try:
        from adcopilot.application.use_cases.score_landing_page import score_landing_page

        result = await score_landing_page(account_id=plan.account_id, session=session)
        return getattr(result, "recommendation_id", None)
    except Exception as exc:
        logger.warning("landing_page_score_failed", plan_id=plan.id, error=str(exc))
        return None
