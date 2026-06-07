# Production environment configuration (LAUNCH-007 / LAUNCH-012)

`Settings.validate_production_config()` runs at API startup (FastAPI lifespan)
and Celery app creation. When `ENV=production` it **refuses to boot** if any
*critical* var below is missing or points at localhost, and if `SECRET_KEY` /
`TOKEN_ENCRYPTION_KEY` still hold their insecure defaults. Set these in the
Railway dashboard for each service.

## Critical — app will not start without these (production)
| Variable | Notes |
|----------|-------|
| `ENV` | Set to `production`. |
| `SECRET_KEY` | Strong random (e.g. `python -c "import secrets;print(secrets.token_urlsafe(48))"`). Signs OAuth state + internal JWTs. |
| `TOKEN_ENCRYPTION_KEY` | Strong random. Encrypts stored Google refresh tokens. |
| `DATABASE_URL` | Managed Postgres URL (not localhost). |
| `REDIS_URL` | Managed Redis URL (not localhost). |
| `APP_URL` | Public frontend URL, e.g. `https://app.adswise.pl`. Also drives CORS. |
| `OAUTH_REDIRECT_URI` | Real API domain `…/oauth/google/callback`; register it in Google Cloud Console. |
| `SUPABASE_JWKS_URL` + `SUPABASE_ISSUER` | Without these, auth silently 401s every request. |
| `LLM_API_KEY` | Anthropic key — required for AI explanations/generation. |
| `GOOGLE_ADS_DEVELOPER_TOKEN` / `GOOGLE_ADS_CLIENT_ID` / `GOOGLE_ADS_CLIENT_SECRET` | Google Ads access (needs Standard token — see LAUNCH-013). |
| `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` | Live keys. Register the webhook at `…/webhooks/stripe`. |
| `STRIPE_STARTER_PRICE_ID` / `STRIPE_PRO_PRICE_ID` / `STRIPE_BUSINESS_PRICE_ID` | Live price IDs. |

## Recommended — not fatal, but you want them in production
| Variable | Why |
|----------|-----|
| `SENTRY_DSN` | Without it you are blind to backend + beat failures. Strongly advised given worker/beat run as separate services. |
| `ADMIN_USER_IDS` | Comma-separated UUIDs. Empty = no admin access (safe, but the admin console is then unusable). |
| `GA4_OAUTH_REDIRECT_URI` | Real API domain `…/oauth/ga4/callback`; only if GA4 connect is offered. |
| `STRIPE_SETUP_FEE_PRICE_ID` | Only if the campaign-launch wizard (deferred) is enabled. |
| `PAGESPEED_API_KEY` | Landing-page scoring; degrades gracefully if unset. |
| `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | Nightly Postgres backups to Cloudflare R2. |

## Frontend (build-time `VITE_*` — see the frontend repo)
`VITE_BACKEND_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` must be
set as build args/vars on the frontend service, or the bundle calls localhost.

## Per-service
- **api**: all of the above + the migration pre-deploy step (`alembic upgrade head`) — see `docs/deploy.md`.
- **worker** & **beat**: same env; beat must run exactly one instance.
