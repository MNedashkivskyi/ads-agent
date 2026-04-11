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

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
