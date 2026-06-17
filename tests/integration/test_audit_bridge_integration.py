"""Integration test: the onboarding bridge through real repositories + Postgres.

Unit tests cover BridgeAuditSessionUseCase with fakes; this exercises the actual
SQL — the customer-id match (get_by_customer_id), the once-only promote() guard,
and set_account_for_session relinking the report. Requires TEST_DATABASE_URL.
"""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from adcopilot.application.use_cases.bridge_audit_session import BridgeAuditSessionUseCase
from adcopilot.domain.audit import AuditStatus, ReportConfidence
from adcopilot.domain.entities import AccountId, GoogleAdsAccount, PlanTier, User, UserId
from adcopilot.infrastructure.db.repositories.audit_repository import (
    SqlAuditSessionRepository,
    SqlWasteReportRepository,
)
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)
from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

_CUSTOMER_ID = "1234567890"


async def _seed_user_account(
    db_session: AsyncSession, customer_id: str
) -> tuple[UserId, AccountId]:
    user_id = UserId(str(uuid.uuid4()))
    await SqlUserRepository(db_session).save(
        User(
            id=user_id,
            email=f"bridge-{uuid.uuid4()}@example.com",
            telegram_chat_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            plan=PlanTier.STARTER,
        )
    )
    account_id = AccountId(str(uuid.uuid4()))
    await SqlGoogleAdsAccountRepository(db_session).save(
        GoogleAdsAccount(
            id=account_id,
            user_id=user_id,
            customer_id=customer_id,
            descriptive_name="Bridge Test",
            currency="PLN",
            timezone="Europe/Warsaw",
            is_manager=False,
            write_enabled=True,
            connected_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )
    return user_id, account_id


async def _seed_session_with_report(db_session: AsyncSession, customer_id: str) -> str:
    sessions = SqlAuditSessionRepository(db_session)
    reports = SqlWasteReportRepository(db_session)
    session = await sessions.create(google_customer_id=customer_id)
    await sessions.set_status(session.id, AuditStatus.READY)
    await reports.create(
        window_start=date(2026, 5, 1),
        window_end=date(2026, 5, 31),
        total_spend_micros=10_000_000_000,
        headline_waste_micros=2_000_000_000,
        measurement_gap_pct=0.3,
        confidence=ReportConfidence.HIGH,
        audit_session_id=session.id,
    )
    return session.id


@pytest.mark.integration
async def test_bridge_promotes_session_and_relinks_report(db_session: AsyncSession) -> None:
    user_id, account_id = await _seed_user_account(db_session, _CUSTOMER_ID)
    session_id = await _seed_session_with_report(db_session, _CUSTOMER_ID)

    sessions = SqlAuditSessionRepository(db_session)
    reports = SqlWasteReportRepository(db_session)
    use_case = BridgeAuditSessionUseCase(
        sessions, SqlGoogleAdsAccountRepository(db_session), reports
    )

    bridged = await use_case.execute(session_id=session_id, user_id=str(user_id))

    assert bridged == str(account_id)
    promoted = await sessions.get(session_id)
    assert promoted is not None
    assert promoted.status is AuditStatus.PROMOTED
    assert promoted.user_id == str(user_id)
    assert promoted.account_id == str(account_id)
    # The waste report is now tied to the account (powers the dashboard banner/meter).
    account_report = await reports.get_for_account(str(account_id))
    assert account_report is not None
    assert account_report.account_id == str(account_id)


@pytest.mark.integration
async def test_bridge_refuses_account_owned_by_other_user(db_session: AsyncSession) -> None:
    _seeded_user, _account = await _seed_user_account(db_session, _CUSTOMER_ID)
    session_id = await _seed_session_with_report(db_session, _CUSTOMER_ID)

    sessions = SqlAuditSessionRepository(db_session)
    use_case = BridgeAuditSessionUseCase(
        sessions, SqlGoogleAdsAccountRepository(db_session), SqlWasteReportRepository(db_session)
    )

    # A different user must not be able to claim the audit for an account it doesn't own.
    bridged = await use_case.execute(session_id=session_id, user_id=str(uuid.uuid4()))

    assert bridged is None
    still = await sessions.get(session_id)
    assert still is not None
    assert still.status is AuditStatus.READY
    assert still.user_id is None
