"""Repository for conversion_outcomes + conversion_uploads (Phase 1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.domain.conversion_outcome import (
    ConversionOutcome,
    ConversionUploadRecord,
    OutcomeStatus,
    UploadStatus,
)
from adcopilot.infrastructure.db.models import ConversionOutcomeModel, ConversionUploadModel


def _to_domain(m: ConversionOutcomeModel) -> ConversionOutcome:
    return ConversionOutcome(
        id=m.id,
        account_id=str(m.account_id),
        gclid=m.gclid,
        gbraid=m.gbraid,
        wbraid=m.wbraid,
        hashed_email=m.hashed_email,
        hashed_phone=m.hashed_phone,
        conversion_action_id=m.conversion_action_id,
        value=float(m.value) if m.value is not None else None,
        currency_code=m.currency_code,
        status=OutcomeStatus(m.status),
        upload_status=UploadStatus(m.upload_status),
        occurred_at=m.occurred_at,
        uploaded_at=m.uploaded_at,
        last_error=m.last_error,
        external_id=m.external_id,
        pending_adjustment=m.pending_adjustment,
        adjusted_at=m.adjusted_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_values(o: ConversionOutcome) -> dict:
    return {
        "id": o.id,
        "account_id": uuid.UUID(o.account_id),
        "gclid": o.gclid,
        "gbraid": o.gbraid,
        "wbraid": o.wbraid,
        "hashed_email": o.hashed_email,
        "hashed_phone": o.hashed_phone,
        "conversion_action_id": o.conversion_action_id,
        "value": o.value,
        "currency_code": o.currency_code,
        "status": o.status.value,
        "upload_status": o.upload_status.value,
        "occurred_at": o.occurred_at,
        "uploaded_at": o.uploaded_at,
        "last_error": o.last_error,
        "external_id": o.external_id,
        "pending_adjustment": o.pending_adjustment,
        "adjusted_at": o.adjusted_at,
        "updated_at": o.updated_at,
    }


class ConversionOutcomeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, outcome: ConversionOutcome) -> None:
        """Insert or update by primary key."""
        values = _to_values(outcome)
        stmt = insert(ConversionOutcomeModel).values(**values)
        update_cols = {k: getattr(stmt.excluded, k) for k in values if k not in ("id", "account_id")}
        stmt = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
        await self._session.execute(stmt)

    async def get(self, outcome_id: uuid.UUID) -> ConversionOutcome | None:
        row = (
            await self._session.execute(
                select(ConversionOutcomeModel).where(ConversionOutcomeModel.id == outcome_id)
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def get_by_external_id(
        self, account_id: str, external_id: str
    ) -> ConversionOutcome | None:
        row = (
            await self._session.execute(
                select(ConversionOutcomeModel).where(
                    ConversionOutcomeModel.account_id == uuid.UUID(account_id),
                    ConversionOutcomeModel.external_id == external_id,
                )
            )
        ).scalar_one_or_none()
        return _to_domain(row) if row else None

    async def list_for_account(
        self, account_id: str, *, status: OutcomeStatus | None = None, limit: int = 100
    ) -> list[ConversionOutcome]:
        stmt = select(ConversionOutcomeModel).where(
            ConversionOutcomeModel.account_id == uuid.UUID(account_id)
        )
        if status is not None:
            stmt = stmt.where(ConversionOutcomeModel.status == status.value)
        stmt = stmt.order_by(ConversionOutcomeModel.created_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_uploadable(self, account_id: str, *, limit: int = 500) -> list[ConversionOutcome]:
        """WON outcomes not yet successfully uploaded (PENDING or FAILED)."""
        stmt = (
            select(ConversionOutcomeModel)
            .where(
                ConversionOutcomeModel.account_id == uuid.UUID(account_id),
                ConversionOutcomeModel.status == OutcomeStatus.WON.value,
                ConversionOutcomeModel.upload_status.in_(
                    (UploadStatus.PENDING.value, UploadStatus.FAILED.value)
                ),
            )
            .order_by(ConversionOutcomeModel.occurred_at.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def list_needing_adjustment(
        self, account_id: str, *, limit: int = 500
    ) -> list[ConversionOutcome]:
        """Uploaded conversions with a pending restate/retract correction."""
        stmt = (
            select(ConversionOutcomeModel)
            .where(
                ConversionOutcomeModel.account_id == uuid.UUID(account_id),
                ConversionOutcomeModel.pending_adjustment.isnot(None),
                ConversionOutcomeModel.upload_status == UploadStatus.UPLOADED.value,
            )
            .order_by(ConversionOutcomeModel.updated_at.asc())
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(r) for r in rows]

    async def mark_uploaded(self, ids: list[uuid.UUID], uploaded_at: datetime) -> None:
        if not ids:
            return
        await self._session.execute(
            update(ConversionOutcomeModel)
            .where(ConversionOutcomeModel.id.in_(ids))
            .values(upload_status=UploadStatus.UPLOADED.value, uploaded_at=uploaded_at, last_error=None)
        )

    async def mark_failed(self, ids: list[uuid.UUID], error: str) -> None:
        if not ids:
            return
        await self._session.execute(
            update(ConversionOutcomeModel)
            .where(ConversionOutcomeModel.id.in_(ids))
            .values(upload_status=UploadStatus.FAILED.value, last_error=error[:1000])
        )


class ConversionUploadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, rec: ConversionUploadRecord) -> None:
        await self._session.execute(
            insert(ConversionUploadModel).values(
                id=rec.id,
                account_id=uuid.UUID(rec.account_id),
                kind=rec.kind,
                outcome_count=rec.outcome_count,
                validate_only=rec.validate_only,
                succeeded=rec.succeeded,
                failed_count=rec.failed_count,
                error_summary=rec.error_summary,
            )
        )
