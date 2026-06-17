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
    # Model used for most LLM work. The "premium" model is used only for the
    # highest-leverage stage (ad-copy) on high-spend (GROWTH) accounts. Defaults
    # to the same model as the default, so tiering is INERT until ops sets
    # LLM_MODEL_PREMIUM to a stronger model (e.g. an Opus snapshot) — no code
    # deploy needed, and no risk of pointing at a model the API key can't use.
    LLM_MODEL_DEFAULT: str = "claude-haiku-4-5-20251001"
    LLM_MODEL_PREMIUM: str = "claude-haiku-4-5-20251001"
    # Max concurrent outbound Google Ads API calls per event loop (throttle) so
    # managing many accounts at once can't exhaust the developer-token quota.
    GOOGLE_ADS_MAX_CONCURRENCY: int = 8
    PAGESPEED_API_KEY: str | None = None

    # ADW-010: RLSA audience auto-add silently writes to Google Ads, bypassing
    # the approve→execute trust model the rest of the product uses. It is
    # deferred from the MVP and OFF by default; set to True to re-enable the
    # weekly automation. (The use case itself is unchanged and still tested.)
    ENABLE_RLSA_AUTOMATION: bool = False

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

    # Free-audit funnel — read-only Google Ads connect (Audit Funnel Phase 0).
    # Separate registered redirect URI for the anonymous audit OAuth callback;
    # must be added in Google Cloud Console alongside OAUTH_REDIRECT_URI.
    AUDIT_OAUTH_REDIRECT_URI: str = "http://localhost:8000/oauth/audit/callback"

    # --- Campaign Intelligence Engine ---------------------------------------
    # DataForSEO — exact search-volume fallback + keyword expansion. Optional;
    # when unset the CIE degrades to Keyword Planner only (no exact fallback,
    # no expansion). Auth is HTTP Basic (login:password).
    DATAFORSEO_LOGIN: str | None = None
    DATAFORSEO_PASSWORD: str | None = None
    # Feature flag + cost guard for the optional expansion step (Phase 2).
    ENABLE_KEYWORD_EXPANSION: bool = False
    # Max DataForSEO requests one expansion run may issue (per-request billing).
    KEYWORD_EXPANSION_MAX_REQUESTS: int = 3
    # Cache TTL (seconds) for validated keyword volumes — 30 days. Beauty
    # keywords repeat across nearly every client in a vertical, so the
    # cross-client hit rate is high and real cost collapses.
    KEYWORD_VOLUME_CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 30
    # Min monthly searches for a keyword to be considered viable.
    KEYWORD_MIN_VIABLE_VOLUME: int = 10
    # Cache TTL (seconds) for near-identical generation inputs (Phase 7.2).
    GENERATION_CACHE_TTL_SECONDS: int = 60 * 60 * 24 * 7

    # Reversible kill-switch for greenfield (brand-new) campaign creation.
    # Default OFF: the product has pivoted to optimizing existing campaigns
    # (optimization pivot, Phase 1). When False, the launch / proposal-editor
    # routers and the PMax creation routes are not served (they 404); flipping
    # it True restores them. Physical deletion of the creation code is deferred
    # to T6.2 after a stabilization window.
    CAMPAIGN_CREATION_ENABLED: bool = False

    # Global kill-switch for auto-apply (Phase 3 / T3.1). Default OFF: even
    # accounts that have opted into auto-apply will not have anything executed
    # automatically until this platform-level flag is turned on. This is the
    # R4 mitigation — a single switch to halt all automated execution.
    AUTO_APPLY_GLOBALLY_ENABLED: bool = False

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

    def assert_secure_for_production(self) -> None:
        """Refuse to run in production with insecure secret defaults.

        Booting with the default SECRET_KEY makes OAuth-state and internal
        JWTs forgeable; the default TOKEN_ENCRYPTION_KEY makes stored Google
        refresh tokens recoverable. Fail loud at startup instead of silently
        shipping them. (LAUNCH-005)
        """
        if not self.is_production:
            return
        offenders = []
        if self.SECRET_KEY == "change-me-in-production":
            offenders.append("SECRET_KEY")
        if self.TOKEN_ENCRYPTION_KEY == "change-me-in-production-32-bytes":
            offenders.append("TOKEN_ENCRYPTION_KEY")
        if offenders:
            raise RuntimeError(
                "Refusing to start in production with insecure default secrets: "
                + ", ".join(offenders)
                + ". Set strong random values in the environment."
            )

    def validate_production_config(self) -> None:
        """Fail-fast on missing/invalid critical production configuration.

        Several env vars degrade *silently* if unset (auth 401s everything,
        OAuth points at localhost, billing 503s). Refuse to boot in production
        until the critical set is present and not pointing at localhost. See
        docs/deploy-env.md for the full list incl. recommended (non-fatal) vars.
        (LAUNCH-007)
        """
        if not self.is_production:
            return
        self.assert_secure_for_production()

        problems: list[str] = []
        # Must be present (None/empty by default).
        required_present = {
            "APP_URL": self.APP_URL,
            "SUPABASE_JWKS_URL": self.SUPABASE_JWKS_URL,
            "SUPABASE_ISSUER": self.SUPABASE_ISSUER,
            "LLM_API_KEY": self.LLM_API_KEY,
            "GOOGLE_ADS_DEVELOPER_TOKEN": self.GOOGLE_ADS_DEVELOPER_TOKEN,
            "GOOGLE_ADS_CLIENT_ID": self.GOOGLE_ADS_CLIENT_ID,
            "GOOGLE_ADS_CLIENT_SECRET": self.GOOGLE_ADS_CLIENT_SECRET,
            "STRIPE_SECRET_KEY": self.STRIPE_SECRET_KEY,
            "STRIPE_WEBHOOK_SECRET": self.STRIPE_WEBHOOK_SECRET,
            "STRIPE_STARTER_PRICE_ID": self.STRIPE_STARTER_PRICE_ID,
            "STRIPE_PRO_PRICE_ID": self.STRIPE_PRO_PRICE_ID,
            "STRIPE_BUSINESS_PRICE_ID": self.STRIPE_BUSINESS_PRICE_ID,
        }
        problems += [f"{name} is not set" for name, val in required_present.items() if not val]

        # Must not point at localhost in production.
        for name, val in {
            "DATABASE_URL": self.DATABASE_URL,
            "REDIS_URL": self.REDIS_URL,
            "OAUTH_REDIRECT_URI": self.OAUTH_REDIRECT_URI,
        }.items():
            if val and "localhost" in val:
                problems.append(f"{name} points at localhost")

        if problems:
            raise RuntimeError(
                "Invalid production configuration — refusing to start:\n  - "
                + "\n  - ".join(problems)
                + "\nSee docs/deploy-env.md."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
