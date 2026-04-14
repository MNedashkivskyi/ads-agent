"""
Integration tests for SQLAlchemy repository adapters.
Requires a running PostgreSQL instance (TEST_DATABASE_URL env var).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from adcopilot.domain.entities import (
    AccountId,
    GoogleAdsAccount,
    OAuthCredentials,
    PlanTier,
    User,
    UserId,
)
from adcopilot.infrastructure.db.repositories.google_ads_account_repository import (
    SqlGoogleAdsAccountRepository,
)
from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
    SqlOAuthCredentialsRepository,
)
from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository

TEST_ENCRYPTION_KEY = "test-encryption-key-32-bytes-ok!"


@pytest.mark.integration
async def test_user_save_then_get_returns_identical(db_session: AsyncSession) -> None:
    repo = SqlUserRepository(db_session)
    user = User(
        id=UserId(str(uuid.uuid4())),
        email=f"test-{uuid.uuid4()}@example.com",
        telegram_chat_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        plan=PlanTier.STARTER,
    )
    saved = await repo.save(user)
    fetched = await repo.get_by_id(user.id)

    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.email == user.email
    assert fetched.plan == user.plan
    assert fetched.telegram_chat_id is None


@pytest.mark.integration
async def test_user_get_by_email(db_session: AsyncSession) -> None:
    repo = SqlUserRepository(db_session)
    email = f"email-{uuid.uuid4()}@example.com"
    user = User(
        id=UserId(str(uuid.uuid4())),
        email=email,
        telegram_chat_id=42,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        plan=PlanTier.GROWTH,
    )
    await repo.save(user)
    fetched = await repo.get_by_email(email)
    assert fetched is not None
    assert fetched.telegram_chat_id == 42


@pytest.mark.integration
async def test_google_ads_account_save_then_get(db_session: AsyncSession) -> None:
    user_repo = SqlUserRepository(db_session)
    acc_repo = SqlGoogleAdsAccountRepository(db_session)

    user_id = UserId(str(uuid.uuid4()))
    user = User(
        id=user_id,
        email=f"ads-{uuid.uuid4()}@example.com",
        telegram_chat_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        plan=PlanTier.STARTER,
    )
    await user_repo.save(user)

    account = GoogleAdsAccount(
        id=AccountId(str(uuid.uuid4())),
        user_id=user_id,
        customer_id="123-456-7890",
        descriptive_name="Acme Ads",
        currency="USD",
        timezone="America/New_York",
        is_manager=False,
        write_enabled=True,
        connected_at=datetime(2026, 1, 2, tzinfo=UTC),
    )
    saved = await acc_repo.save(account)
    fetched = await acc_repo.get(account.id)

    assert fetched is not None
    assert fetched.id == saved.id
    assert fetched.customer_id == "123-456-7890"
    assert fetched.write_enabled is True

    accounts = await acc_repo.list_for_user(user_id)
    assert len(accounts) == 1
    assert accounts[0].id == account.id


@pytest.mark.integration
async def test_oauth_credentials_encrypted_at_rest(db_session: AsyncSession) -> None:
    """Verify that the refresh_token stored in DB is not the plaintext value."""
    # First create a user and account
    user_repo = SqlUserRepository(db_session)
    acc_repo = SqlGoogleAdsAccountRepository(db_session)
    creds_repo = SqlOAuthCredentialsRepository(db_session, TEST_ENCRYPTION_KEY)

    user_id = UserId(str(uuid.uuid4()))
    await user_repo.save(
        User(
            id=user_id,
            email=f"enc-{uuid.uuid4()}@example.com",
            telegram_chat_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            plan=PlanTier.STARTER,
        )
    )
    account_id = AccountId(str(uuid.uuid4()))
    await acc_repo.save(
        GoogleAdsAccount(
            id=account_id,
            user_id=user_id,
            customer_id="999",
            descriptive_name="Enc Test",
            currency="USD",
            timezone="UTC",
            is_manager=False,
            write_enabled=False,
            connected_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )

    plaintext_token = "my-super-secret-refresh-token"
    creds = OAuthCredentials(
        account_id=account_id,
        refresh_token=plaintext_token,
        access_token=None,
        expires_at=None,
    )
    await creds_repo.save(creds)

    # Verify retrieval decrypts correctly
    fetched = await creds_repo.get(account_id)
    assert fetched is not None
    assert fetched.refresh_token == plaintext_token

    # Verify the raw DB value is NOT the plaintext and has Fernet format.
    # Acceptance criterion: "Raw SQL query shows encrypted blobs in
    # oauth_credentials.refresh_token".
    result = await db_session.execute(
        text("SELECT refresh_token_encrypted FROM oauth_credentials WHERE account_id = :aid"),
        {"aid": str(account_id)},
    )
    row = result.fetchone()
    assert row is not None
    raw_value = row[0]
    assert raw_value != plaintext_token
    assert plaintext_token not in raw_value
    assert len(raw_value) > len(plaintext_token)
    # Fernet v0 tokens always begin with the base64 form of \x80 ("gAAAAA").
    assert raw_value.startswith("gAAAAA"), (
        f"Expected Fernet-format ciphertext on disk, got prefix {raw_value[:10]!r}"
    )
