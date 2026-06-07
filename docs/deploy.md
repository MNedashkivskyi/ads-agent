# Deployment (Railway) — services & process (LAUNCH-008)

The repo deploys as **one image** to **multiple Railway services**. The
per-service start/pre-deploy commands are committed as scripts (below) so they
are reproducible, not dashboard-only. Env vars: see `docs/deploy-env.md`.

## Required services
| Service | Start command | Notes |
|---------|---------------|-------|
| `adswise-api` | `sh scripts/start-api.sh` | Pre-deploy: `sh scripts/migrate.sh`. Healthcheck: `/health`. |
| `adswise-worker` | `sh scripts/start-worker.sh` | Celery worker. Scale horizontally as needed. |
| `adswise-beat` | `sh scripts/start-beat.sh` | Celery beat — **exactly ONE instance** (duplicates double-fire every scheduled job). |
| `adswise-postgres` | Railway managed | Enable automated backups. |
| `adswise-redis` | Railway managed | Broker + result backend + rate-limit store. |

> If the worker or beat service is missing/stopped, **all** background jobs
> (nightly snapshots, detection, digests, anomaly + spend-cap alerts, backups)
> stop silently — set `SENTRY_DSN` so beat cron-monitors alert you.

## Migrations
Run on every deploy via the API service **pre-deploy** command
`sh scripts/migrate.sh` (`alembic upgrade head`). Do not skip it — new code
against an unmigrated DB will error at runtime.

## Config validation
On startup the API and Celery call `Settings.validate_production_config()`,
which refuses to boot in production if critical env vars are missing/insecure
(see `docs/deploy-env.md`). A failed boot here means a missing/incorrect var.

## Frontend
Separate Railway service from the `frontend/` repo (static SPA via nginx). It
needs build-time `VITE_BACKEND_URL`, `VITE_SUPABASE_URL`,
`VITE_SUPABASE_PUBLISHABLE_KEY`.

See `RAILWAY_DEPLOYMENT.md` for the original step-by-step dashboard setup.
