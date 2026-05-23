"""Repository for qs_improvement_plans table."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from adcopilot.infrastructure.db.models import QSImprovementPlanModel


class QSImprovementPlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, plan_id: str) -> QSImprovementPlan | None:
        result = await self._session.execute(
            select(QSImprovementPlanModel).where(
                QSImprovementPlanModel.id == uuid.UUID(plan_id)
            )
        )
        row = result.scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list_for_account(self, account_id: str) -> list[QSImprovementPlan]:
        result = await self._session.execute(
            select(QSImprovementPlanModel)
            .where(QSImprovementPlanModel.account_id == uuid.UUID(account_id))
            .order_by(QSImprovementPlanModel.created_at.desc())
        )
        return [_to_domain(r) for r in result.scalars().all()]

    async def list_measuring_past_window(self, now: datetime) -> list[QSImprovementPlan]:
        result = await self._session.execute(
            select(QSImprovementPlanModel)
            .where(QSImprovementPlanModel.status == QSPlanStatus.MEASURING.value)
            .where(QSImprovementPlanModel.measurement_ends_at <= now)
        )
        return [_to_domain(r) for r in result.scalars().all()]

    async def list_active_for_account(self, account_id: str) -> list[QSImprovementPlan]:
        """Active = PROPOSED or IN_PROGRESS or MEASURING."""
        result = await self._session.execute(
            select(QSImprovementPlanModel)
            .where(QSImprovementPlanModel.account_id == uuid.UUID(account_id))
            .where(
                QSImprovementPlanModel.status.in_([
                    QSPlanStatus.PROPOSED.value,
                    QSPlanStatus.IN_PROGRESS.value,
                    QSPlanStatus.MEASURING.value,
                ])
            )
        )
        return [_to_domain(r) for r in result.scalars().all()]

    async def save(self, plan: QSImprovementPlan) -> None:
        existing = await self._session.get(QSImprovementPlanModel, uuid.UUID(plan.id))
        if existing:
            existing.status = plan.status.value
            existing.current_avg_qs = plan.current_avg_qs
            existing.prescribed_actions = _actions_to_json(plan.prescribed_actions)
            existing.current_metrics = _metrics_to_json(plan.current_metrics)
            existing.evaluation_summary_pl = plan.evaluation_summary_pl
            existing.started_at = plan.started_at
            existing.measurement_ends_at = plan.measurement_ends_at
            existing.completed_at = plan.completed_at
        else:
            row = QSImprovementPlanModel(
                id=uuid.UUID(plan.id),
                account_id=uuid.UUID(plan.account_id),
                keyword_criterion_ids=plan.keyword_criterion_ids,
                target_ad_group_resource_name=plan.target_ad_group_resource_name,
                current_avg_qs=plan.current_avg_qs,
                target_qs=plan.target_qs,
                bottleneck_component=plan.bottleneck_component.value,
                prescribed_actions=_actions_to_json(plan.prescribed_actions),
                status=plan.status.value,
                baseline_metrics=_metrics_to_json(plan.baseline_metrics),
                current_metrics=_metrics_to_json(plan.current_metrics),
                evaluation_summary_pl=plan.evaluation_summary_pl,
                created_at=plan.created_at,
                started_at=plan.started_at,
                measurement_ends_at=plan.measurement_ends_at,
                completed_at=plan.completed_at,
            )
            self._session.add(row)
        await self._session.flush()


def _to_domain(row: QSImprovementPlanModel) -> QSImprovementPlan:
    actions_raw = row.prescribed_actions or []
    actions = [
        QSAction(
            action_type=QSActionType(a["action_type"]),
            status=QSActionStatus(a["status"]),
            recommendation_id=a.get("recommendation_id"),
            details_json=a.get("details_json", {}),
        )
        for a in actions_raw
    ]

    baseline = _json_to_metrics(row.baseline_metrics)
    current = _json_to_metrics(row.current_metrics)

    return QSImprovementPlan(
        id=QSImprovementPlanId(str(row.id)),
        account_id=str(row.account_id),
        keyword_criterion_ids=row.keyword_criterion_ids or [],
        target_ad_group_resource_name=row.target_ad_group_resource_name,
        current_avg_qs=row.current_avg_qs,
        target_qs=row.target_qs,
        bottleneck_component=QSBottleneckComponent(row.bottleneck_component),
        prescribed_actions=actions,
        status=QSPlanStatus(row.status),
        baseline_metrics=baseline,
        current_metrics=current,
        evaluation_summary_pl=row.evaluation_summary_pl,
        created_at=row.created_at,
        started_at=row.started_at,
        measurement_ends_at=row.measurement_ends_at,
        completed_at=row.completed_at,
    )


def _actions_to_json(actions: list[QSAction]) -> list[dict]:
    return [
        {
            "action_type": a.action_type.value,
            "status": a.status.value,
            "recommendation_id": a.recommendation_id,
            "details_json": a.details_json,
        }
        for a in actions
    ]


def _metrics_to_json(metrics: QSMetrics | None) -> dict | None:
    if metrics is None:
        return None
    return {
        "avg_qs": metrics.avg_qs,
        "avg_cpc_micros": metrics.avg_cpc_micros,
        "avg_ctr": metrics.avg_ctr,
    }


def _json_to_metrics(data: dict | None) -> QSMetrics | None:
    if not data:
        return None
    return QSMetrics(
        avg_qs=data.get("avg_qs"),
        avg_cpc_micros=data.get("avg_cpc_micros"),
        avg_ctr=data.get("avg_ctr"),
    )
