"""Performance reports API endpoints."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["reports"])


class GenerateReportRequest(BaseModel):
    account_id: str
    period_start: str  # YYYY-MM-DD
    period_end: str


class ReportMetadata(BaseModel):
    id: str
    user_id: str
    account_id: str
    period_start: str
    period_end: str
    summary_pl: str | None
    created_at: str


class ReportListResponse(BaseModel):
    reports: list[ReportMetadata]


def _row_to_metadata(row: object) -> ReportMetadata:
    return ReportMetadata(
        id=str(row.id),
        user_id=str(row.user_id),
        account_id=str(row.account_id),
        period_start=row.period_start.isoformat(),
        period_end=row.period_end.isoformat(),
        summary_pl=row.summary_pl,
        created_at=row.created_at.isoformat(),
    )


@router.post("/{user_id}/reports/generate", response_model=ReportMetadata)
async def generate_report(
    user_id: str,
    body: GenerateReportRequest,
    current_user: CurrentUser,
) -> ReportMetadata:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from datetime import date

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.generate_performance_report import generate_performance_report
    from adcopilot.config import get_settings
    from adcopilot.infrastructure.db.repositories.prompt_version_repository import SqlPromptVersionRepository
    from adcopilot.infrastructure.llm.anthropic_client import AnthropicClient as AnthropicLLMClient
    from adcopilot.infrastructure.reporting.pdf_renderer import render_performance_report_pdf

    try:
        period_start = date.fromisoformat(body.period_start)
        period_end = date.fromisoformat(body.period_end)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid date format: {exc}") from exc

    settings = get_settings()
    llm = AnthropicLLMClient(api_key=settings.LLM_API_KEY or "")
    engine = create_async_engine(settings.DATABASE_URL)

    try:
        async with AsyncSession(engine) as session:
            prompt_repo = SqlPromptVersionRepository(session)
            report_data = await generate_performance_report(
                user_id=user_id,
                account_id=body.account_id,
                period_start=period_start,
                period_end=period_end,
                session=session,
                llm=llm,
                prompt_repo=prompt_repo,
            )

            pdf_bytes = render_performance_report_pdf(report_data)

            report_id = uuid.uuid4()
            await session.execute(
                text(
                    """
                    INSERT INTO performance_reports
                        (id, user_id, account_id, period_start, period_end, report_data, summary_pl, pdf_bytes)
                    VALUES
                        (:id, :user_id, :account_id, :period_start, :period_end, :report_data::jsonb, :summary_pl, :pdf_bytes)
                    """
                ),
                {
                    "id": str(report_id),
                    "user_id": user_id,
                    "account_id": body.account_id,
                    "period_start": period_start,
                    "period_end": period_end,
                    "report_data": __import__("json").dumps(report_data),
                    "summary_pl": report_data.get("summary_pl"),
                    "pdf_bytes": pdf_bytes,
                },
            )
            await session.commit()

            row = (
                await session.execute(
                    text("SELECT * FROM performance_reports WHERE id = :id"),
                    {"id": str(report_id)},
                )
            ).mappings().one()
    finally:
        await engine.dispose()

    return ReportMetadata(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        account_id=str(row["account_id"]),
        period_start=row["period_start"].isoformat(),
        period_end=row["period_end"].isoformat(),
        summary_pl=row["summary_pl"],
        created_at=row["created_at"].isoformat(),
    )


@router.get("/{user_id}/reports", response_model=ReportListResponse)
async def list_reports(
    user_id: str,
    current_user: CurrentUser,
) -> ReportListResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT id, user_id, account_id, period_start, period_end, summary_pl, created_at "
                        "FROM performance_reports WHERE user_id = :user_id ORDER BY created_at DESC"
                    ),
                    {"user_id": user_id},
                )
            ).mappings().all()
    finally:
        await engine.dispose()

    reports = [
        ReportMetadata(
            id=str(r["id"]),
            user_id=str(r["user_id"]),
            account_id=str(r["account_id"]),
            period_start=r["period_start"].isoformat(),
            period_end=r["period_end"].isoformat(),
            summary_pl=r["summary_pl"],
            created_at=r["created_at"].isoformat(),
        )
        for r in rows
    ]
    return ReportListResponse(reports=reports)


@router.get("/{user_id}/reports/{report_id}", response_model=ReportMetadata)
async def get_report(
    user_id: str,
    report_id: str,
    current_user: CurrentUser,
) -> ReportMetadata:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT id, user_id, account_id, period_start, period_end, summary_pl, created_at "
                        "FROM performance_reports WHERE id = :id AND user_id = :user_id"
                    ),
                    {"id": report_id, "user_id": user_id},
                )
            ).mappings().one_or_none()
    finally:
        await engine.dispose()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    return ReportMetadata(
        id=str(row["id"]),
        user_id=str(row["user_id"]),
        account_id=str(row["account_id"]),
        period_start=row["period_start"].isoformat(),
        period_end=row["period_end"].isoformat(),
        summary_pl=row["summary_pl"],
        created_at=row["created_at"].isoformat(),
    )


@router.get("/{user_id}/reports/{report_id}/download")
async def download_report(
    user_id: str,
    report_id: str,
    current_user: CurrentUser,
) -> Response:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden")

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.config import get_settings

    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT pdf_bytes FROM performance_reports WHERE id = :id AND user_id = :user_id"
                    ),
                    {"id": report_id, "user_id": user_id},
                )
            ).mappings().one_or_none()
    finally:
        await engine.dispose()

    if not row:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_bytes = row["pdf_bytes"]
    if not pdf_bytes:
        raise HTTPException(status_code=404, detail="PDF not available for this report")

    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="report_{report_id}.pdf"',
        },
    )
