"""QS Improvement Plans API."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["qs-improvement"])


class QSActionResponse(BaseModel):
    action_type: str
    status: str
    recommendation_id: str | None
    details_json: dict


class QSMetricsResponse(BaseModel):
    avg_qs: float | None
    avg_cpc_micros: int | None
    avg_ctr: float | None


class QSImprovementPlanResponse(BaseModel):
    id: str
    account_id: str
    keyword_criterion_ids: list[int]
    target_ad_group_resource_name: str | None
    current_avg_qs: float | None
    target_qs: float
    bottleneck_component: str
    prescribed_actions: list[QSActionResponse]
    status: str
    baseline_metrics: QSMetricsResponse | None
    current_metrics: QSMetricsResponse | None
    evaluation_summary_pl: str | None
    created_at: str
    started_at: str | None
    measurement_ends_at: str | None
    completed_at: str | None


class CreateQSImprovementPlanRequest(BaseModel):
    keyword_criterion_ids: list[int] | None = None


def _plan_to_response(plan) -> QSImprovementPlanResponse:
    return QSImprovementPlanResponse(
        id=plan.id,
        account_id=plan.account_id,
        keyword_criterion_ids=plan.keyword_criterion_ids,
        target_ad_group_resource_name=plan.target_ad_group_resource_name,
        current_avg_qs=plan.current_avg_qs,
        target_qs=plan.target_qs,
        bottleneck_component=plan.bottleneck_component.value,
        prescribed_actions=[
            QSActionResponse(
                action_type=a.action_type.value,
                status=a.status.value,
                recommendation_id=a.recommendation_id,
                details_json=a.details_json,
            )
            for a in plan.prescribed_actions
        ],
        status=plan.status.value,
        baseline_metrics=QSMetricsResponse(
            avg_qs=plan.baseline_metrics.avg_qs,
            avg_cpc_micros=plan.baseline_metrics.avg_cpc_micros,
            avg_ctr=plan.baseline_metrics.avg_ctr,
        )
        if plan.baseline_metrics
        else None,
        current_metrics=QSMetricsResponse(
            avg_qs=plan.current_metrics.avg_qs,
            avg_cpc_micros=plan.current_metrics.avg_cpc_micros,
            avg_ctr=plan.current_metrics.avg_ctr,
        )
        if plan.current_metrics
        else None,
        evaluation_summary_pl=plan.evaluation_summary_pl,
        created_at=plan.created_at.isoformat(),
        started_at=plan.started_at.isoformat() if plan.started_at else None,
        measurement_ends_at=plan.measurement_ends_at.isoformat()
        if plan.measurement_ends_at
        else None,
        completed_at=plan.completed_at.isoformat() if plan.completed_at else None,
    )


@router.get(
    "/{user_id}/quality-score/improvement-plans", response_model=list[QSImprovementPlanResponse]
)
async def list_qs_improvement_plans(
    user_id: str,
    current_user: CurrentUser,
) -> list[QSImprovementPlanResponse]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.account_repository import AccountRepository
    from adcopilot.infrastructure.db.repositories.qs_improvement_plan_repository import (
        QSImprovementPlanRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = AccountRepository(session)
            accounts = await account_repo.list_for_user(user_id)
            if not accounts:
                raise HTTPException(status_code=404, detail="No accounts found")
            repo = QSImprovementPlanRepository(session)
            plans = await repo.list_for_account(str(accounts[0].id))
    finally:
        await engine.dispose()
    return [_plan_to_response(p) for p in plans]


@router.post("/{user_id}/quality-score/improvement-plans", response_model=QSImprovementPlanResponse)
async def create_qs_improvement_plan(
    user_id: str,
    body: CreateQSImprovementPlanRequest,
    current_user: CurrentUser,
) -> QSImprovementPlanResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.create_qs_improvement_plan import (
        create_qs_improvement_plan as uc,
    )
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.account_repository import AccountRepository
    from adcopilot.infrastructure.db.repositories.qs_improvement_plan_repository import (
        QSImprovementPlanRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            account_repo = AccountRepository(session)
            accounts = await account_repo.list_for_user(user_id)
            if not accounts:
                raise HTTPException(status_code=404, detail="No accounts found")
            try:
                plan = await uc(
                    account_id=str(accounts[0].id),
                    session=session,
                    keyword_criterion_ids=body.keyword_criterion_ids,
                )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            repo = QSImprovementPlanRepository(session)
            await repo.save(plan)
            await session.commit()
    finally:
        await engine.dispose()
    return _plan_to_response(plan)


@router.get(
    "/{user_id}/quality-score/improvement-plans/{plan_id}", response_model=QSImprovementPlanResponse
)
async def get_qs_improvement_plan(
    user_id: str,
    plan_id: str,
    current_user: CurrentUser,
) -> QSImprovementPlanResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.qs_improvement_plan_repository import (
        QSImprovementPlanRepository,
    )

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            repo = QSImprovementPlanRepository(session)
            plan = await repo.get(plan_id)
            if not plan:
                raise HTTPException(status_code=404, detail="Plan not found")
    finally:
        await engine.dispose()
    return _plan_to_response(plan)


@router.post(
    "/{user_id}/quality-score/improvement-plans/{plan_id}/execute",
    response_model=QSImprovementPlanResponse,
)
async def execute_qs_improvement_plan(
    user_id: str,
    plan_id: str,
    current_user: CurrentUser,
) -> QSImprovementPlanResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.execute_qs_improvement_plan import (
        execute_qs_improvement_plan as uc,
    )
    from adcopilot.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            try:
                plan = await uc(plan_id=plan_id, session=session)
                await session.commit()
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
    finally:
        await engine.dispose()
    return _plan_to_response(plan)
