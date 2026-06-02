"""Measurement Foundation API — Phase 0 measurement-health diagnostic."""

from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api.auth_middleware import CurrentUser

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api", tags=["measurement"])


class MeasurementSubScoreResponse(BaseModel):
    key: str
    label: str
    status: str
    detail: str


class ConversionActionSummaryResponse(BaseModel):
    name: str
    category: str
    status: str
    all_conversions: float
    health: str


class MeasurementHealthResponse(BaseModel):
    overall_status: str
    subscores: list[MeasurementSubScoreResponse]
    conversion_actions: list[ConversionActionSummaryResponse]


# --- Lead intake / Offline Conversion Import (Phase 2) --------------------


class LeadIntakeRequest(BaseModel):
    gclid: str | None = None
    gbraid: str | None = None
    wbraid: str | None = None
    email: str | None = None  # hashed server-side; raw PII is never stored
    phone: str | None = None
    conversion_action_id: int | None = None
    external_id: str | None = None


class LeadResponse(BaseModel):
    id: str
    status: str
    upload_status: str
    value: float | None
    currency_code: str
    conversion_action_id: int | None
    has_attribution: bool
    occurred_at: str | None
    external_id: str | None
    created_at: str


class LeadWinRequest(BaseModel):
    value: float
    currency_code: str | None = None
    occurred_at: str | None = None  # ISO 8601; defaults to now (UTC)


class UploadRequest(BaseModel):
    validate_only: bool = True  # default to a safe dry-run


class UploadResultResponse(BaseModel):
    received: int
    succeeded: int
    failed: int
    errors: list[str]
    validate_only: bool


class ConsentSnippetResponse(BaseModel):
    snippet: str
    instructions_pl: str


@router.get("/{user_id}/measurement/consent-snippet", response_model=ConsentSnippetResponse)
async def get_consent_snippet(
    user_id: str,
    current_user: CurrentUser,
) -> ConsentSnippetResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    from adcopilot.domain.conversion_tracking.consent_mode import (
        INSTRUCTIONS_PL,
        consent_mode_v2_snippet,
    )

    return ConsentSnippetResponse(snippet=consent_mode_v2_snippet(), instructions_pl=INSTRUCTIONS_PL)


async def _detect_consent_mode_v2(session, account_id) -> bool:
    """Best-effort: fetch the account's landing page and detect Consent Mode v2."""
    import json
    import uuid

    from sqlalchemy import desc, select

    from adcopilot.infrastructure.consent_checker import fetch_measurement_signals
    from adcopilot.infrastructure.db.models import AdSnapshotModel

    acct_uuid = account_id if isinstance(account_id, uuid.UUID) else uuid.UUID(str(account_id))
    row = (
        await session.execute(
            select(AdSnapshotModel.final_urls_json)
            .where(
                AdSnapshotModel.account_id == acct_uuid,
                AdSnapshotModel.final_urls_json.isnot(None),
            )
            .order_by(desc(AdSnapshotModel.snapshot_date))
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        return False
    try:
        urls = json.loads(row) if isinstance(row, str) else row
    except (ValueError, TypeError):
        return False
    if not urls:
        return False
    signals = await fetch_measurement_signals(urls[0])
    return signals.consent_mode_v2


@router.get("/{user_id}/measurement/health", response_model=MeasurementHealthResponse)
async def get_measurement_health(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeasurementHealthResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import uuid

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.assess_measurement_health import (
        assess_measurement_health,
    )
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.models import GA4CredentialsModel
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )
    from adcopilot.infrastructure.google_ads.queries_adapter import GoogleAdsQueriesAdapter

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account_repo = SqlGoogleAdsAccountRepository(session)
            credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)

            accounts = await account_repo.list_for_user(UserId(user_id))
            if not accounts:
                raise HTTPException(status_code=404, detail="No Google Ads accounts found")

            account = accounts[0]
            credentials = await credentials_repo.get(AccountId(account.id))
            if credentials is None:
                raise HTTPException(status_code=422, detail="Google Ads account not connected")

            google_ads = GoogleAdsQueriesAdapter(settings)
            snapshots = await google_ads.list_conversion_actions(
                credentials.refresh_token, account.customer_id
            )
            enhanced_enabled = await google_ads.get_enhanced_conversions_for_leads_enabled(
                credentials.refresh_token, account.customer_id
            )

            ga4_linked = (
                await session.execute(
                    select(GA4CredentialsModel.id).where(
                        GA4CredentialsModel.account_id == uuid.UUID(str(account.id))
                    )
                )
            ).scalar_one_or_none() is not None

            consent_v2 = await _detect_consent_mode_v2(session, account.id)

            report = assess_measurement_health(
                snapshots,
                ga4_linked=ga4_linked,
                enhanced_conversions_enabled=enhanced_enabled,
                consent_mode_v2_detected=consent_v2,
            )
    finally:
        await engine.dispose()

    logger.info(
        "measurement_health.complete",
        user_id=user_id,
        overall=report.overall_status.value,
        actions=len(report.conversion_actions),
        ga4_linked=ga4_linked,
    )

    return MeasurementHealthResponse(
        overall_status=report.overall_status.value,
        subscores=[
            MeasurementSubScoreResponse(
                key=s.key, label=s.label, status=s.status.value, detail=s.detail
            )
            for s in report.subscores
        ],
        conversion_actions=[
            ConversionActionSummaryResponse(
                name=c.name,
                category=c.category,
                status=c.status,
                all_conversions=c.all_conversions,
                health=c.health,
            )
            for c in report.conversion_actions
        ],
    )


# ---------------------------------------------------------------------------
# Lead intake + Offline Conversion Import
# ---------------------------------------------------------------------------


def _lead_to_response(o) -> LeadResponse:
    return LeadResponse(
        id=str(o.id),
        status=o.status.value,
        upload_status=o.upload_status.value,
        value=o.value,
        currency_code=o.currency_code,
        conversion_action_id=o.conversion_action_id,
        has_attribution=o.has_click_identifier() or o.has_hashed_identifier(),
        occurred_at=o.occurred_at.isoformat() if o.occurred_at else None,
        external_id=o.external_id,
        created_at=o.created_at.isoformat(),
    )


async def _resolve_account(session, user_id: str):
    """Return (account, refresh_token) for the user's primary account or raise."""
    from adcopilot.config import get_settings
    from adcopilot.domain.entities import AccountId, UserId
    from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
        SqlGoogleAdsAccountRepository,
    )
    from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
        SqlOAuthCredentialsRepository,
    )

    settings = get_settings()
    account_repo = SqlGoogleAdsAccountRepository(session)
    credentials_repo = SqlOAuthCredentialsRepository(session, settings.TOKEN_ENCRYPTION_KEY)
    accounts = await account_repo.list_for_user(UserId(user_id))
    if not accounts:
        raise HTTPException(status_code=404, detail="No Google Ads accounts found")
    account = accounts[0]
    credentials = await credentials_repo.get(AccountId(account.id))
    refresh_token = credentials.refresh_token if credentials else None
    return account, refresh_token


@router.post("/{user_id}/measurement/leads", response_model=LeadResponse)
async def intake_lead(
    user_id: str,
    body: LeadIntakeRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LeadResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.domain.conversion_outcome import ConversionOutcome
    from adcopilot.infrastructure.db.repositories.conversion_outcome_repository import (
        ConversionOutcomeRepository,
    )
    from adcopilot.infrastructure.hashing import hash_email, hash_phone

    if not any([body.gclid, body.gbraid, body.wbraid, body.email, body.phone]):
        raise HTTPException(
            status_code=422,
            detail="Lead wymaga identyfikatora atrybucji (gclid/gbraid/wbraid) lub e-mail/telefon.",
        )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            # Dedup on external_id within the account.
            repo = ConversionOutcomeRepository(session)
            if body.external_id:
                existing = await repo.get_by_external_id(str(account.id), body.external_id)
                if existing is not None:
                    return _lead_to_response(existing)
            outcome = ConversionOutcome(
                account_id=str(account.id),
                gclid=body.gclid,
                gbraid=body.gbraid,
                wbraid=body.wbraid,
                hashed_email=hash_email(body.email),  # raw PII discarded; only hash stored
                hashed_phone=hash_phone(body.phone),
                conversion_action_id=body.conversion_action_id,
                external_id=body.external_id,
            )
            await repo.save(outcome)
    finally:
        await engine.dispose()
    return _lead_to_response(outcome)


@router.get("/{user_id}/measurement/leads", response_model=list[LeadResponse])
async def list_leads(
    user_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[LeadResponse]:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.conversion_outcome_repository import (
        ConversionOutcomeRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            repo = ConversionOutcomeRepository(session)
            outcomes = await repo.list_for_account(str(account.id), limit=200)
    finally:
        await engine.dispose()
    return [_lead_to_response(o) for o in outcomes]


@router.post("/{user_id}/measurement/leads/{outcome_id}/win", response_model=LeadResponse)
async def win_lead(
    user_id: str,
    outcome_id: str,
    body: LeadWinRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LeadResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import uuid
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.conversion_outcome_repository import (
        ConversionOutcomeRepository,
    )

    if body.occurred_at:
        try:
            occurred = datetime.fromisoformat(body.occurred_at)
        except ValueError as e:
            raise HTTPException(status_code=422, detail="Nieprawidłowy format occurred_at") from e
    else:
        occurred = datetime.now(UTC)

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            repo = ConversionOutcomeRepository(session)
            outcome = await repo.get(uuid.UUID(outcome_id))
            if outcome is None or outcome.account_id != str(account.id):
                raise HTTPException(status_code=404, detail="Lead not found")
            from adcopilot.domain.conversion_outcome import OutcomeStatus, UploadStatus

            try:
                # If the conversion was already uploaded, a value change is a
                # RESTATEMENT (correction), not a fresh win.
                if (
                    outcome.upload_status is UploadStatus.UPLOADED
                    and outcome.status is OutcomeStatus.WON
                ):
                    outcome.restate(body.value)
                else:
                    outcome.mark_won(
                        value=body.value, occurred_at=occurred, currency_code=body.currency_code
                    )
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e)) from e
            await repo.save(outcome)
    finally:
        await engine.dispose()
    return _lead_to_response(outcome)


@router.post("/{user_id}/measurement/leads/{outcome_id}/lose", response_model=LeadResponse)
async def lose_lead(
    user_id: str,
    outcome_id: str,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LeadResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.infrastructure.db.repositories.conversion_outcome_repository import (
        ConversionOutcomeRepository,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, _ = await _resolve_account(session, user_id)
            repo = ConversionOutcomeRepository(session)
            outcome = await repo.get(uuid.UUID(outcome_id))
            if outcome is None or outcome.account_id != str(account.id):
                raise HTTPException(status_code=404, detail="Lead not found")
            from adcopilot.domain.conversion_outcome import UploadStatus

            # An already-uploaded conversion that's now lost must be RETRACTED.
            if outcome.upload_status is UploadStatus.UPLOADED:
                outcome.retract()
            else:
                outcome.mark_lost()
            await repo.save(outcome)
    finally:
        await engine.dispose()
    return _lead_to_response(outcome)


@router.post("/{user_id}/measurement/leads/upload", response_model=UploadResultResponse)
async def upload_leads(
    user_id: str,
    body: UploadRequest,
    current_user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UploadResultResponse:
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from adcopilot.application.use_cases.upload_offline_conversions import (
        upload_offline_conversions,
    )
    from adcopilot.domain.exceptions import GoogleAdsAuthError, GoogleAdsUnavailable
    from adcopilot.infrastructure.db.repositories.conversion_outcome_repository import (
        ConversionOutcomeRepository,
        ConversionUploadRepository,
    )
    from adcopilot.infrastructure.google_ads.measurement_mutations_adapter import (
        GoogleAdsMeasurementUploadAdapter,
    )

    engine = create_async_engine(settings.DATABASE_URL)
    try:
        async with AsyncSession(engine) as session, session.begin():
            account, refresh_token = await _resolve_account(session, user_id)
            if not refresh_token:
                raise HTTPException(status_code=422, detail="Google Ads account not connected")
            try:
                result = await upload_offline_conversions(
                    account_id=str(account.id),
                    customer_id=account.customer_id,
                    refresh_token=refresh_token,
                    outcome_repo=ConversionOutcomeRepository(session),
                    upload_repo=ConversionUploadRepository(session),
                    uploader=GoogleAdsMeasurementUploadAdapter(settings),
                    validate_only=body.validate_only,
                )
            except (GoogleAdsAuthError, GoogleAdsUnavailable) as e:
                raise HTTPException(status_code=502, detail=str(e)) from e
    finally:
        await engine.dispose()
    return UploadResultResponse(
        received=result.received,
        succeeded=result.succeeded,
        failed=result.failed,
        errors=result.errors,
        validate_only=result.validate_only,
    )
