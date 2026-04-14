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
    TELEGRAM_BOT_TOKEN: str | None = None
    # Public base URL of this service (e.g. https://app.example.com).
    # When set, the app registers a Telegram webhook on startup and webhook
    # mode is used instead of polling.  Leave blank for local development.
    TELEGRAM_WEBHOOK_URL: str | None = None
    # Public URL of the web application — used to build deep-links in Telegram
    # messages (e.g. the re-authentication link sent when a Google Ads token
    # is revoked).  Example: https://app.example.com
    APP_URL: str | None = None
    LLM_API_KEY: str | None = None

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
