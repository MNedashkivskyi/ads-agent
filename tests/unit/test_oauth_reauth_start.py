"""Unit tests for the reauth path of ``GET /oauth/google/start``.

When an account's OAuth session expires it is flagged ``needs_reauth`` and the
frontend's "Reauth" button hits ``/oauth/google/start?...&reauth=1``.  Because
the expired account already occupies a quota slot, the per-plan limit check
that guards new connections must be *skipped* for reauth — otherwise the user
is bounced straight back to the app with ``error=quota_exceeded`` and the
button appears to do nothing (the bug this fix addresses).

These tests stub the repositories so they run without a database.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from adcopilot.config import Settings, get_settings
from adcopilot.interfaces.api import oauth as oauth_module
from adcopilot.interfaces.api.oauth import _get_db_session
from adcopilot.main import create_app

GOOGLE_CONSENT_HOST = "accounts.google.com"


def _settings() -> Settings:
    return Settings(
        DATABASE_URL="postgresql+asyncpg://unused/unused",
        SECRET_KEY="test-secret-key",
        TOKEN_ENCRYPTION_KEY="test-encryption-key-32-bytes-ok!",
        GOOGLE_ADS_CLIENT_ID="test-client-id",
        GOOGLE_ADS_CLIENT_SECRET="test-client-secret",
        APP_URL="https://app.example.com",
        OAUTH_REDIRECT_URI="https://api.example.com/oauth/google/callback",
    )


def _build_client(monkeypatch, *, existing_accounts) -> TestClient:
    """Wire a TestClient whose repositories are stubbed in-memory.

    ``existing_accounts`` is the list ``list_for_user`` returns — each item only
    needs a ``needs_reauth`` attribute for these tests.
    """
    settings = _settings()

    # A starter user (1-account plan) so a single existing account == at quota.
    fake_user = SimpleNamespace(plan=SimpleNamespace(value="starter"))

    user_repo = MagicMock()
    user_repo.ensure_exists = AsyncMock(return_value=fake_user)
    acc_repo = MagicMock()
    acc_repo.list_for_user = AsyncMock(return_value=existing_accounts)

    monkeypatch.setattr(oauth_module, "SqlUserRepository", lambda _session: user_repo)
    monkeypatch.setattr(oauth_module, "SqlGoogleAdsAccountRepository", lambda _session: acc_repo)

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: settings

    async def _fake_session():
        # The stubbed repos ignore the session; commit() must be awaitable.
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[_get_db_session] = _fake_session
    # follow_redirects=False so we can inspect the 302 target.
    return TestClient(app, follow_redirects=False)


def test_reauth_at_quota_redirects_to_google(monkeypatch) -> None:
    """reauth=1 with an expired account at quota must reach Google's consent."""
    expired = SimpleNamespace(needs_reauth=True)
    client = _build_client(monkeypatch, existing_accounts=[expired])

    resp = client.get(
        "/oauth/google/start",
        params={"user_id": "11111111-1111-1111-1111-111111111111", "reauth": "1"},
    )

    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert GOOGLE_CONSENT_HOST in location, location
    assert "quota_exceeded" not in location


def test_add_account_at_quota_is_blocked(monkeypatch) -> None:
    """Without reauth, an at-quota user must still be blocked (no bypass)."""
    existing = SimpleNamespace(needs_reauth=False)
    client = _build_client(monkeypatch, existing_accounts=[existing])

    resp = client.get(
        "/oauth/google/start",
        params={"user_id": "11111111-1111-1111-1111-111111111111"},
    )

    assert resp.status_code == 302, resp.text
    location = resp.headers["location"]
    assert "error=quota_exceeded" in location
    assert GOOGLE_CONSENT_HOST not in location


def test_first_connection_redirects_to_google(monkeypatch) -> None:
    """A user with no accounts (normal first connect) reaches Google's consent."""
    client = _build_client(monkeypatch, existing_accounts=[])

    resp = client.get(
        "/oauth/google/start",
        params={"user_id": "11111111-1111-1111-1111-111111111111"},
    )

    assert resp.status_code == 302, resp.text
    assert GOOGLE_CONSENT_HOST in resp.headers["location"]
