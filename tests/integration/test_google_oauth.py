"""
Integration test for Google OAuth flow.
Mocks Google's token endpoint using respx.
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from adcopilot.config import Settings
from adcopilot.domain.entities import PlanTier, User, UserId
from adcopilot.infrastructure.db.models import Base
from adcopilot.infrastructure.db.repositories.oauth_credentials_repository import (
    SqlOAuthCredentialsRepository,
)
from adcopilot.infrastructure.db.repositories.user_repository import SqlUserRepository
from adcopilot.main import create_app

TEST_ENCRYPTION_KEY = "test-encryption-key-32-bytes-ok!"


@pytest.mark.integration
async def test_oauth_callback_stores_encrypted_credentials(db_session: AsyncSession) -> None:
    """Full OAuth callback flow: mocked token exchange, stores encrypted credentials."""
    import os

    test_db_url = os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://adcopilot:adcopilot@localhost:5432/adcopilot_test",
    )

    engine = create_async_engine(test_db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    settings = Settings(
        DATABASE_URL=test_db_url,
        SECRET_KEY="test-secret-key",
        TOKEN_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
        GOOGLE_ADS_CLIENT_ID="test-client-id",
        GOOGLE_ADS_CLIENT_SECRET="test-client-secret",
    )

    # Create a test user in the DB
    async with AsyncSession(engine) as session:
        user_repo = SqlUserRepository(session)
        user_id = str(uuid.uuid4())
        user = User(
            id=UserId(user_id),
            email=f"oauth-test-{uuid.uuid4()}@example.com",
            telegram_chat_id=None,
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            plan=PlanTier.STARTER,
        )
        await user_repo.save(user)
        await session.commit()

    refresh_token = "ya29.test-refresh-token"
    access_token = "ya29.test-access-token"

    # Mock Google token endpoint
    with respx.mock:
        respx.post("https://oauth2.googleapis.com/token").mock(
            return_value=Response(
                200,
                json={
                    "refresh_token": refresh_token,
                    "access_token": access_token,
                    "expires_in": 3600,
                    "token_type": "Bearer",
                },
            )
        )

        # Mock the Google Ads client list_accessible_customers
        with patch(
            "adcopilot.interfaces.api.oauth.GoogleAdsClientAdapter"
        ) as mock_ads_cls:
            mock_ads_instance = AsyncMock()
            mock_ads_instance.list_accessible_customers.return_value = [
                "customers/1234567890"
            ]
            mock_ads_cls.return_value = mock_ads_instance

            from adcopilot.interfaces.api.oauth import _make_state_jwt

            state = _make_state_jwt(user_id, settings.SECRET_KEY)

            app = create_app()
            app.dependency_overrides = {}

            # Override settings dependency
            from adcopilot.config import get_settings
            app.dependency_overrides[get_settings] = lambda: settings

            with TestClient(app, raise_server_exceptions=True) as client:
                resp = client.get(
                    "/oauth/google/callback",
                    params={"code": "test-auth-code", "state": state},
                )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["user_id"] == user_id
    assert "customers/1234567890" in data["linked_customer_ids"]

    # Verify credentials were stored encrypted
    async with AsyncSession(engine) as session:
        creds_repo = SqlOAuthCredentialsRepository(session, TEST_ENCRYPTION_KEY)
        from adcopilot.domain.entities import AccountId

        account_id = AccountId(
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"{user_id}/customers/1234567890"))
        )
        stored_creds = await creds_repo.get(account_id)
        assert stored_creds is not None
        assert stored_creds.refresh_token == refresh_token

    await engine.dispose()
