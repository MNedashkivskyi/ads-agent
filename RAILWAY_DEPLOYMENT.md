# Deploying AdCopilot on Railway

This guide covers deploying the full AdCopilot stack — API, Celery worker, Celery beat scheduler, PostgreSQL, and Redis — on [Railway](https://railway.app), plus the companion `approve-ads-agent` frontend.

---

## Architecture overview

Railway models each process as an independent **service**. AdCopilot requires five services total:

| Service | Type | Start command |
|---------|------|---------------|
| **api** | Web (this repo) | `uvicorn adcopilot.main:app --host 0.0.0.0 --port $PORT --workers 2 --proxy-headers --forwarded-allow-ips '*'` |
| **worker** | Worker (this repo) | `celery -A adcopilot.interfaces.worker.celery_app:celery_app worker --loglevel=warning -Q default --concurrency=4 --prefetch-multiplier=1 --max-tasks-per-child=200` |
| **beat** | Worker (this repo) | `celery -A adcopilot.interfaces.worker.celery_app:celery_app beat --loglevel=warning --schedule /tmp/celerybeat-schedule` |
| **postgres** | Railway plugin | managed |
| **redis** | Railway plugin | managed |

The `approve-ads-agent` frontend lives in a separate Railway project (or as a sixth service) — see [Frontend deployment](#frontend-approve-ads-agent).

> **Beat is a singleton.** Never scale the beat service beyond 1 replica. Duplicate beat instances produce double-scheduled tasks (two nightly snapshot runs, two daily digests, etc.).

---

## Prerequisites

- A [Railway](https://railway.app) account (Hobby plan or higher)
- Railway CLI: `npm i -g @railway/cli` then `railway login`
- Your repository pushed to GitHub and linked to Railway
- All third-party credentials ready (see [Environment variables](#environment-variables))

---

## Step 1 — Create a new Railway project

```bash
railway new          # follow the prompts; choose "Empty project"
```

Or create a project from the Railway dashboard: **New Project → Empty Project**.

Give the project a name, e.g. `adcopilot-production`.

---

## Step 2 — Add managed databases

Inside the project, click **+ New** → **Database** for each:

1. **PostgreSQL** — Railway provisions a Postgres 16 instance and injects `DATABASE_URL` into your project environment automatically.
2. **Redis** — Railway provisions Redis and injects `REDIS_URL`.

> Railway injects these variables using their internal reference system. You will reference them when setting service variables in Step 5.

---

## Step 3 — Create the API service

1. **+ New → GitHub Repo** → select `ads-agent`.
2. Name the service **api**.
3. Railway auto-detects `railway.toml` and uses the `Dockerfile` builder with the configured start command.
4. The `preDeployCommand` in `railway.toml` runs `alembic upgrade head` automatically before each deploy — no manual migration step needed.

---

## Step 4 — Create worker and beat services

Railway allows multiple services from the same repository with different start commands.

### Worker service

1. **+ New → GitHub Repo** → select `ads-agent` again.
2. Name the service **worker**.
3. In service settings → **Deploy** tab, set a custom **Start Command**:
   ```
   celery -A adcopilot.interfaces.worker.celery_app:celery_app worker --loglevel=warning -Q default --concurrency=4 --prefetch-multiplier=1 --max-tasks-per-child=200
   ```
4. Disable the health check (worker has no HTTP endpoint): leave **Healthcheck Path** empty.
5. Set **Replicas** to 1 (scale up later if needed).

### Beat service

1. **+ New → GitHub Repo** → select `ads-agent` again.
2. Name the service **beat**.
3. Set **Start Command**:
   ```
   celery -A adcopilot.interfaces.worker.celery_app:celery_app beat --loglevel=warning --schedule /tmp/celerybeat-schedule
   ```
4. Disable health check.
5. **Keep Replicas at exactly 1. Never increase this.**

---

## Step 5 — Environment variables

Set these variables on **all three services** (api, worker, beat) via the Railway dashboard **Variables** tab. Use Railway's **Shared Variables** feature or set them per-service.

### Shared variables (recommended)

Railway lets you define variables at the project level that are available across all services. Go to **Project Settings → Shared Variables** and add each variable once.

### Required variables

#### Database & cache

| Variable | Value | Notes |
|----------|-------|-------|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Railway reference — auto-injects the Postgres URL. The app expects the `postgresql+asyncpg://` scheme. See note below. |
| `REDIS_URL` | `${{Redis.REDIS_URL}}` | Railway reference — auto-injects the Redis URL. |

> **asyncpg scheme**: Railway's Postgres plugin injects a `postgresql://` URL. The app's SQLAlchemy layer requires `postgresql+asyncpg://`. Create a custom variable:
> ```
> DATABASE_URL = postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
> ```
> This assembles the correct asyncpg DSN from Railway's individual Postgres variables.

#### Application

| Variable | Value | Notes |
|----------|-------|-------|
| `ENV` | `production` | Enables production logging, strict security |
| `LOG_LEVEL` | `WARNING` | Use `INFO` for verbose logging |
| `SECRET_KEY` | _(random 64-char string)_ | JWT signing key. Generate: `openssl rand -hex 32` |
| `TOKEN_ENCRYPTION_KEY` | _(random 32-byte base64)_ | OAuth token encryption. Generate: `python -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"` |

#### Google Ads

| Variable | Value | Notes |
|----------|-------|-------|
| `GOOGLE_ADS_DEVELOPER_TOKEN` | from Google Cloud Console | Required for all Google Ads API calls |
| `GOOGLE_ADS_CLIENT_ID` | from Google Cloud Console | OAuth 2.0 web app client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | from Google Cloud Console | OAuth 2.0 client secret |

#### Telegram

| Variable | Value | Notes |
|----------|-------|-------|
| `TELEGRAM_BOT_TOKEN` | from [@BotFather](https://t.me/botfather) | Required for Telegram notifications |
| `TELEGRAM_WEBHOOK_URL` | `https://<your-api-domain>` | Public URL of the **api** service. Railway assigns a domain automatically — copy it from the service's **Settings → Domains** tab. |

#### LLM (Anthropic Claude)

| Variable | Value | Notes |
|----------|-------|-------|
| `LLM_API_KEY` | Anthropic API key | Powers recommendation explanations |

#### Stripe billing

| Variable | Value | Notes |
|----------|-------|-------|
| `STRIPE_SECRET_KEY` | from Stripe Dashboard | `sk_live_...` in production |
| `STRIPE_WEBHOOK_SECRET` | from Stripe → Webhooks | `whsec_...` — obtained after creating the webhook endpoint |
| `STRIPE_STARTER_PRICE_ID` | `price_...` | Starter plan price ID |
| `STRIPE_PRO_PRICE_ID` | `price_...` | Pro plan price ID |
| `STRIPE_BUSINESS_PRICE_ID` | `price_...` | Business plan price ID (optional) |

#### Frontend URL

| Variable | Value | Notes |
|----------|-------|-------|
| `APP_URL` | `https://<your-frontend-domain>` | Public URL of the `approve-ads-agent` frontend. Used for deep-links in Telegram messages (e.g. re-auth links). |

---

## Step 6 — Configure Stripe webhook

After the api service is deployed and has a public domain:

1. In the Stripe Dashboard → **Developers → Webhooks**, click **Add endpoint**.
2. Endpoint URL: `https://<your-api-domain>/billing/webhook`
3. Select events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`, `invoice.payment_failed`
4. Copy the signing secret and set it as `STRIPE_WEBHOOK_SECRET` in Railway.

---

## Step 7 — Configure Google OAuth redirect URI

In Google Cloud Console → **APIs & Services → Credentials** → your OAuth 2.0 client:

Add the following to **Authorized redirect URIs**:
```
https://<your-api-domain>/oauth/callback
```

---

## Step 8 — Configure Telegram bot commands (one-time)

After the api service is running:

```bash
# From your local machine with .env populated
railway run python scripts/setup_telegram_bot.py
```

Or run it from the Railway shell:

```bash
railway shell --service api
python scripts/setup_telegram_bot.py
```

---

## Step 9 — Verify deployment

```bash
# Check the health endpoint
curl https://<your-api-domain>/health
# Expected: {"status":"ok","db":"ok"}
```

Check service logs in the Railway dashboard or via CLI:

```bash
railway logs --service api
railway logs --service worker
railway logs --service beat
```

---

## Database migrations

Migrations run automatically via `preDeployCommand = "alembic upgrade head"` in `railway.toml` on every api deployment. If a migration fails, Railway aborts the deploy and keeps the previous version live.

To run migrations manually:

```bash
railway run --service api alembic upgrade head
```

To create a new migration after changing SQLAlchemy models:

```bash
railway run --service api alembic revision --autogenerate -m "describe your change"
```

---

## Scaling

### API replicas

Scale the api service horizontally from the Railway dashboard → **Settings → Replicas**.

> The API is stateless (all state in Postgres + Redis) so it scales without coordination.

### Worker replicas

Add more worker replicas to increase background task throughput. Each replica runs 4 concurrent Celery processes.

```bash
# Via Railway dashboard: Settings → Replicas → increase count
```

### Beat replicas

**Do not scale beat above 1 replica.** A second beat instance will double-schedule all periodic tasks.

---

## Custom domain

1. In the api service → **Settings → Domains**, click **+ Custom Domain**.
2. Add a CNAME record in your DNS pointing to the Railway-provided hostname.
3. Railway provisions a TLS certificate automatically via Let's Encrypt.
4. Update `TELEGRAM_WEBHOOK_URL` to use the custom domain.

---

## Environment promotion (staging → production)

Railway supports multiple environments per project (e.g. `production` and `staging`). To create a staging environment:

1. In your project, click the environment selector → **+ New Environment**.
2. Name it `staging`.
3. Override sensitive variables (Stripe test keys, separate Google OAuth client, etc.) in the staging environment.
4. Deploy feature branches to staging; merge to `master` deploys to production.

---

## Frontend: approve-ads-agent

`approve-ads-agent` is the web UI for AdCopilot. Deploy it as a separate Railway service:

1. **+ New → GitHub Repo** → select `approve-ads-agent`.
2. Railway auto-detects the framework (Next.js / Vite / etc.) and configures the build automatically.
3. Set the following environment variable:
   ```
   NEXT_PUBLIC_API_URL=https://<your-api-domain>
   ```
   (Adjust the variable name to match the frontend's configuration.)
4. After deployment, copy the frontend domain and set it as `APP_URL` on the api, worker, and beat services.

The frontend and API can share the same Railway **project** or live in separate projects — there is no strict requirement either way.

---

## Rollback

Railway keeps the previous deployment image. To roll back:

1. Go to the service → **Deployments** tab.
2. Click the previous successful deployment → **Rollback**.

If the rollback requires downgrading the database schema:

```bash
railway run --service api alembic downgrade -1
```

Then trigger the rollback in the Railway UI.

---

## Monitoring and observability

- **Health check**: `GET /health` — returns `{"status":"ok","db":"ok"}` on success, `503` if Postgres is unreachable.
- **Logs**: Railway streams structured JSON logs in real time from the dashboard or `railway logs`.
- **Metrics**: Railway provides basic CPU/memory graphs per service in the dashboard.
- **Error tracking**: Set `SENTRY_DSN` in the environment and instrument `adcopilot/main.py` with the Sentry SDK for error aggregation.

---

## Cost estimate (Hobby plan, March 2025)

| Service | vCPU | RAM | Approx. monthly cost |
|---------|------|-----|---------------------|
| api (1 replica) | 0.5 | 512 MB | ~$5–8 |
| worker (1 replica) | 1.0 | 768 MB | ~$8–12 |
| beat (1 replica) | 0.25 | 128 MB | ~$2–3 |
| PostgreSQL | managed | 1 GB | ~$5 |
| Redis | managed | 256 MB | ~$3 |
| **Total** | | | **~$23–31/month** |

Costs vary with actual usage. Railway charges for compute time and egress.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `DATABASE_URL` connection errors | asyncpg scheme not set | Use the `postgresql+asyncpg://` assembled URL (see Step 5) |
| Telegram webhook not registering | `TELEGRAM_WEBHOOK_URL` not set or wrong | Set to the exact public URL of the api service including `https://` |
| Beat scheduling double tasks | More than 1 beat replica | Scale beat back to exactly 1 |
| `alembic upgrade head` fails on deploy | Migration incompatible with live schema | Roll back deploy, fix migration, redeploy |
| Worker not processing tasks | `REDIS_URL` mismatch between api and worker | Ensure both services reference the same Redis variable |
| Stripe webhook signature error | `STRIPE_WEBHOOK_SECRET` wrong or endpoint URL wrong | Verify endpoint URL matches `/billing/webhook` and secret matches Stripe dashboard |
