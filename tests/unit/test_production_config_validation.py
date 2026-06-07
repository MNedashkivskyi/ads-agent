"""LAUNCH-007: production config validation refuses to boot when incomplete."""

from __future__ import annotations

import pytest

_STRONG = dict(
    SECRET_KEY="a-strong-random-secret-value-1234567890",
    TOKEN_ENCRYPTION_KEY="another-strong-random-32byte-key-xyz",
)

_COMPLETE = dict(
    ENV="production",
    DATABASE_URL="postgresql+asyncpg://u:p@db.internal:5432/app",
    REDIS_URL="redis://cache.internal:6379/0",
    APP_URL="https://app.example.com",
    OAUTH_REDIRECT_URI="https://api.example.com/oauth/google/callback",
    SUPABASE_JWKS_URL="https://x.supabase.co/auth/v1/.well-known/jwks.json",
    SUPABASE_ISSUER="https://x.supabase.co/auth/v1",
    LLM_API_KEY="sk-ant-x",
    GOOGLE_ADS_DEVELOPER_TOKEN="t",
    GOOGLE_ADS_CLIENT_ID="cid",
    GOOGLE_ADS_CLIENT_SECRET="csecret",
    STRIPE_SECRET_KEY="sk_live_x",
    STRIPE_WEBHOOK_SECRET="whsec_x",
    STRIPE_STARTER_PRICE_ID="price_a",
    STRIPE_PRO_PRICE_ID="price_b",
    STRIPE_BUSINESS_PRICE_ID="price_c",
    **_STRONG,
)


def test_complete_production_config_passes() -> None:
    from adcopilot.config import Settings

    Settings(**_COMPLETE).validate_production_config()  # must not raise


def test_missing_critical_var_raises() -> None:
    from adcopilot.config import Settings

    cfg = dict(_COMPLETE)
    cfg.pop("SUPABASE_JWKS_URL")
    with pytest.raises(RuntimeError) as exc:
        Settings(**cfg).validate_production_config()
    assert "SUPABASE_JWKS_URL" in str(exc.value)


def test_localhost_oauth_redirect_raises() -> None:
    from adcopilot.config import Settings

    cfg = dict(_COMPLETE)
    cfg["OAUTH_REDIRECT_URI"] = "http://localhost:8000/oauth/google/callback"
    with pytest.raises(RuntimeError) as exc:
        Settings(**cfg).validate_production_config()
    assert "OAUTH_REDIRECT_URI" in str(exc.value)


def test_dev_is_noop() -> None:
    from adcopilot.config import Settings

    Settings(ENV="dev").validate_production_config()  # must not raise
