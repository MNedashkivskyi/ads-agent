from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://adcopilot:adcopilot@localhost:5432/adcopilot"
    REDIS_URL: str = "redis://localhost:6379/0"
    ENV: str = "dev"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = "change-me-in-production"
    TOKEN_ENCRYPTION_KEY: str = "change-me-in-production-32-bytes"

    GOOGLE_ADS_DEVELOPER_TOKEN: str | None = None
    GOOGLE_ADS_CLIENT_ID: str | None = None
    GOOGLE_ADS_CLIENT_SECRET: str | None = None
    # Public URL of the web application — used to build deep-links
    # (e.g. the re-authentication link sent when a Google Ads token is revoked).
    # Example: https://app.example.com
    APP_URL: str | None = None
    # Full URL that Google redirects to after OAuth consent.
    # Must be registered in Google Cloud Console → Credentials → Authorized redirect URIs.
    # Example (Railway):  https://ads-agent-dev.up.railway.app/oauth/google/callback
    # Example (local):    http://localhost:8000/oauth/google/callback
    OAUTH_REDIRECT_URI: str = "http://localhost:8000/oauth/google/callback"
    LLM_API_KEY: str | None = None
    PAGESPEED_API_KEY: str | None = None

    # Comma-separated list of user UUIDs that have admin access to /api/admin/* endpoints.
    ADMIN_USER_IDS: str = ""

    # Supabase JWT secret — used to verify JWTs issued by Supabase auth.
    # Find it in Supabase project → Settings → API → JWT Secret.
    # Deprecated in favour of SUPABASE_JWKS_URL (asymmetric key verification).
    SUPABASE_JWT_SECRET: str | None = None

    # Supabase JWKS URL — used to verify Supabase JWTs via public-key (RS256/ES256).
    # No shared secret needed.  Format: https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
    SUPABASE_JWKS_URL: str | None = None

    # Supabase issuer URL — used for JWT issuer claim validation.
    # Format: https://<project-ref>.supabase.co/auth/v1
    SUPABASE_ISSUER: str | None = None

    # Telegram Bot API token — used to send proactive reminders to users.
    # Optional; when not set, Telegram notifications are skipped.
    TELEGRAM_BOT_TOKEN: str | None = None

    # Google Analytics 4 — Data API (read-only).
    # Uses the same OAuth client as Google Ads.
    GA4_OAUTH_REDIRECT_URI: str = "http://localhost:8000/oauth/ga4/callback"

    STRIPE_SECRET_KEY: str | None = None
    STRIPE_WEBHOOK_SECRET: str | None = None
    STRIPE_STARTER_PRICE_ID: str | None = None
    STRIPE_PRO_PRICE_ID: str | None = None
    STRIPE_BUSINESS_PRICE_ID: str | None = None

    # Sentry observability.  DSN is optional — the app runs fine without
    # Sentry, but when DSN is set all unhandled exceptions in the API,
    # Celery workers, and Telegram bot are reported.  Sample rate controls
    # performance tracing for the hot paths (snapshot / detection / execute).
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 0.1

    # Cloudflare R2 — used for nightly Postgres backups.
    # R2_ENDPOINT_URL is derived from R2_ACCOUNT_ID when not set explicitly.
    R2_ACCOUNT_ID: str | None = None
    R2_ACCESS_KEY_ID: str | None = None
    R2_SECRET_ACCESS_KEY: str | None = None
    R2_BUCKET_NAME: str = "adcopilot-backups"

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
