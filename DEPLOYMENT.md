# AdCopilot — Production Deployment Guide

This document covers deploying AdCopilot to a single-VPS production server.
The stack runs entirely in Docker containers orchestrated by
`docker-compose.prod.yml`.

---

## Table of contents

1. [Server requirements](#1-server-requirements)
2. [Firewall setup](#2-firewall-setup)
3. [Secret management](#3-secret-management)
4. [Environment variables reference](#4-environment-variables-reference)
5. [Building and pushing the image](#5-building-and-pushing-the-image)
6. [First-time deployment](#6-first-time-deployment)
7. [Updating to a new release](#7-updating-to-a-new-release)
8. [Database migrations](#8-database-migrations)
9. [Backup and restore](#9-backup-and-restore)
10. [Monitoring and observability](#10-monitoring-and-observability)
11. [Rollback procedure](#11-rollback-procedure)
12. [Scaling considerations](#12-scaling-considerations)

---

## 1. Server requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB SSD | 40 GB SSD |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |

Install Docker Engine (not Docker Desktop) and the Compose plugin:

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # re-login after this
docker compose version          # must be >= 2.20
```

---

## 2. Firewall setup

Allow only the ports Caddy needs from the internet. Everything else
(`5432`, `6379`, `8000`) stays on the internal Docker network.

```bash
# UFW example
sudo ufw default deny incoming
sudo ufw allow ssh
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp   # HTTP/3
sudo ufw enable
```

> **Important**: Docker bypasses UFW for container port bindings added with
> the `ports:` key. The production compose file intentionally omits host port
> bindings for postgres, redis, and the app — only Caddy exposes ports 80/443.

---

## 3. Secret management

All secrets are passed to containers through environment variables.
The recommended approach depends on your infrastructure:

### Option A — `.env.prod` file (simplest)

Suitable for a single VPS with no external secrets store.

```bash
# On the server — restrict permissions so only root/deploy user can read it
cp .env.example .env.prod
chmod 600 .env.prod
# Edit .env.prod and fill in every value (see section 4)
```

The production compose file reads from `.env.prod` automatically via
`env_file: .env.prod`.

> **Never commit `.env.prod` to version control.** It is listed in
> `.gitignore`.

### Option B — CI/CD environment injection (recommended for automated pipelines)

For GitHub Actions, GitLab CI, or similar:

1. Store each secret as a repository/pipeline secret in your CI/CD system.
2. In your deploy job, write them to `.env.prod` on the server:

```yaml
# GitHub Actions example (deploy step)
- name: Write .env.prod
  run: |
    ssh deploy@$HOST "cat > ~/adcopilot/.env.prod" <<EOF
    DATABASE_URL=${{ secrets.DATABASE_URL }}
    SECRET_KEY=${{ secrets.SECRET_KEY }}
    TOKEN_ENCRYPTION_KEY=${{ secrets.TOKEN_ENCRYPTION_KEY }}
    TELEGRAM_BOT_TOKEN=${{ secrets.TELEGRAM_BOT_TOKEN }}
    TELEGRAM_WEBHOOK_URL=https://${{ vars.DOMAIN }}/telegram/webhook
    APP_URL=https://${{ vars.DOMAIN }}
    GOOGLE_ADS_DEVELOPER_TOKEN=${{ secrets.GOOGLE_ADS_DEVELOPER_TOKEN }}
    GOOGLE_ADS_CLIENT_ID=${{ secrets.GOOGLE_ADS_CLIENT_ID }}
    GOOGLE_ADS_CLIENT_SECRET=${{ secrets.GOOGLE_ADS_CLIENT_SECRET }}
    STRIPE_SECRET_KEY=${{ secrets.STRIPE_SECRET_KEY }}
    STRIPE_WEBHOOK_SECRET=${{ secrets.STRIPE_WEBHOOK_SECRET }}
    LLM_API_KEY=${{ secrets.LLM_API_KEY }}
    EOF
```

### Option C — Docker Secrets (Docker Swarm only)

If you are running Docker Swarm, use native Docker secrets:

```bash
echo "my-secret-value" | docker secret create secret_key -
```

Adapt the compose file to use `secrets:` references instead of
`env_file`. See the
[Docker Secrets documentation](https://docs.docker.com/engine/swarm/secrets/).

### Rotation

When rotating a secret (e.g. `SECRET_KEY` or `TOKEN_ENCRYPTION_KEY`):
1. Update the value in `.env.prod` (or your secrets store).
2. Re-deploy: `make prod-deploy` (see section 7).
3. If rotating `TOKEN_ENCRYPTION_KEY`, existing stored OAuth tokens are
   encrypted with the old key and will fail to decrypt. Either re-encrypt
   stored tokens or ask all users to reconnect their Google Ads accounts.

---

## 4. Environment variables reference

Copy `.env.example` to `.env.prod` and set every variable:

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | ✓ | PostgreSQL async DSN — `postgresql+asyncpg://adcopilot:<pass>@postgres:5432/adcopilot` |
| `REDIS_URL` | ✓ | Redis DSN — `redis://redis:6379/0` |
| `ENV` | ✓ | Must be `production` |
| `LOG_LEVEL` | | `WARNING` recommended for production |
| `SECRET_KEY` | ✓ | 32+ character random string for JWT signing |
| `TOKEN_ENCRYPTION_KEY` | ✓ | Exactly 32 bytes (base64-encoded) for OAuth token encryption |
| `TELEGRAM_BOT_TOKEN` | ✓ | Bot token from @BotFather |
| `TELEGRAM_WEBHOOK_URL` | ✓ | `https://<DOMAIN>` — triggers webhook mode instead of polling |
| `APP_URL` | ✓ | `https://<DOMAIN>` — used in Telegram re-auth deep-links |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | ✓ | From Google Ads API Center |
| `GOOGLE_ADS_CLIENT_ID` | ✓ | OAuth 2.0 client ID |
| `GOOGLE_ADS_CLIENT_SECRET` | ✓ | OAuth 2.0 client secret |
| `LLM_API_KEY` | ✓ | Anthropic API key |
| `STRIPE_SECRET_KEY` | ✓ | Stripe live secret key |
| `STRIPE_WEBHOOK_SECRET` | ✓ | Stripe webhook signing secret |
| `STRIPE_STARTER_PRICE_ID` | ✓ | Stripe price ID for the Starter plan |
| `STRIPE_PRO_PRICE_ID` | ✓ | Stripe price ID for the Pro plan |
| `STRIPE_BUSINESS_PRICE_ID` | | Stripe price ID for Business plan (optional) |

Additionally, the production compose reads two **deploy-time** variables
that are NOT part of `.env.prod`:

| Variable | Where to set | Description |
|----------|-------------|-------------|
| `DOMAIN` | Shell / CI env | Public hostname, e.g. `app.example.com` |
| `APP_IMAGE` | Shell / CI env | Full image tag, e.g. `ghcr.io/org/ads-agent:sha-abc1234` |
| `POSTGRES_PASSWORD` | Shell / CI env | Matches the password in `DATABASE_URL` |

Generate secure values for `SECRET_KEY` and `TOKEN_ENCRYPTION_KEY`:

```bash
# SECRET_KEY (any length ≥ 32)
python3 -c "import secrets; print(secrets.token_hex(32))"

# TOKEN_ENCRYPTION_KEY (must be exactly 32 bytes, base64-encoded)
python3 -c "import secrets, base64; print(base64.b64encode(secrets.token_bytes(32)).decode())"
```

---

## 5. Building and pushing the image

Build once, deploy the same image to production (never `build:` on the server).

```bash
# Build with Git SHA tag for traceability
GIT_SHA=$(git rev-parse --short HEAD)
IMAGE=ghcr.io/your-org/ads-agent

docker build -t ${IMAGE}:${GIT_SHA} -t ${IMAGE}:latest .

# Push to registry
docker push ${IMAGE}:${GIT_SHA}
docker push ${IMAGE}:latest
```

For GitHub Actions, use the `docker/build-push-action` workflow. The CI
pipeline in `.github/workflows/` runs tests and type checks before building.

---

## 6. First-time deployment

```bash
# 1. SSH into the server and clone the repository
git clone https://github.com/your-org/ads-agent.git ~/adcopilot
cd ~/adcopilot

# 2. Create the secrets file (see section 3)
cp .env.example .env.prod
nano .env.prod          # fill in all values; set ENV=production

# 3. Pull the production image
export APP_IMAGE=ghcr.io/your-org/ads-agent:latest
export DOMAIN=app.example.com
export POSTGRES_PASSWORD=<strong-random-password>

docker compose -f docker-compose.prod.yml pull

# 4. Start postgres and redis first; run migrations before starting the app
docker compose -f docker-compose.prod.yml up -d postgres redis
sleep 5

# 5. Run database migrations
docker compose -f docker-compose.prod.yml run --rm \
  -e DATABASE_URL="postgresql+asyncpg://adcopilot:${POSTGRES_PASSWORD}@postgres:5432/adcopilot" \
  app uv run alembic upgrade head

# 6. Start all remaining services
docker compose -f docker-compose.prod.yml up -d

# 7. Verify everything is healthy
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs app --tail=50

# 8. Check TLS (Caddy needs a minute to obtain the certificate)
curl -I https://${DOMAIN}/health
```

A `Makefile` shortcut is also provided:

```bash
export APP_IMAGE=... DOMAIN=... POSTGRES_PASSWORD=...
make prod-up
make prod-migrate
```

---

## 7. Updating to a new release

```bash
# On the server (or via CI/CD deploy job)
cd ~/adcopilot

# Pull new code and the new image
git pull origin master
export APP_IMAGE=ghcr.io/your-org/ads-agent:<new-sha>

# Pull the new image first (zero downtime window)
docker compose -f docker-compose.prod.yml pull app worker beat

# Run migrations before starting the new app version
docker compose -f docker-compose.prod.yml run --rm app uv run alembic upgrade head

# Rolling restart — Compose restarts containers one at a time
docker compose -f docker-compose.prod.yml up -d --no-deps app worker beat
```

> **Note on migrations**: Alembic migrations are run as a one-off container
> (`run --rm`) before the new app code is deployed.  Migrations must be
> backwards-compatible with the previous app version (additive only — no
> column drops or renames in a single step).

---

## 8. Backup and restore

### Automated daily backup

```bash
# /etc/cron.d/adcopilot-backup
0 3 * * * root docker exec adcopilot-prod-postgres-1 \
  pg_dump -U adcopilot adcopilot | gzip \
  > /backups/adcopilot-$(date +\%Y\%m\%d).sql.gz

# Retain 30 days
0 4 * * * root find /backups -name "adcopilot-*.sql.gz" -mtime +30 -delete
```

### Manual restore

```bash
# Stop the app to prevent writes during restore
docker compose -f docker-compose.prod.yml stop app worker beat

# Restore
gunzip -c /backups/adcopilot-20260401.sql.gz | \
  docker exec -i adcopilot-prod-postgres-1 \
  psql -U adcopilot adcopilot

# Restart
docker compose -f docker-compose.prod.yml start app worker beat
```

---

## 10. Monitoring and observability

### Structured logs

All containers emit JSON logs via the `json-file` driver with automatic
rotation (configured in `docker-compose.prod.yml`).

```bash
# Tail all logs
docker compose -f docker-compose.prod.yml logs -f

# App only
docker compose -f docker-compose.prod.yml logs -f app
```

### Health check endpoint

```bash
curl https://${DOMAIN}/health
# → {"status": "ok", "db": "ok"}
```

The `/health` endpoint verifies database connectivity.  Wire it to an
uptime monitor (UptimeRobot, Better Uptime, etc.) to get alerted on
downtime.

### Optional: Sentry error tracking

Set `SENTRY_DSN` in `.env.prod` and add the `sentry-sdk[fastapi]`
dependency to capture exceptions automatically from the FastAPI app and
Celery worker.

### Optional: Prometheus metrics

Instrument with `prometheus-fastapi-instrumentator` and expose a `/metrics`
endpoint, then scrape from a Prometheus instance.

---

## 11. Rollback procedure

```bash
# Deploy the previous image tag
export APP_IMAGE=ghcr.io/your-org/ads-agent:<previous-sha>
docker compose -f docker-compose.prod.yml pull app worker beat
docker compose -f docker-compose.prod.yml up -d --no-deps app worker beat
```

If the migration must be reversed:

```bash
# Identify the previous migration revision
docker compose -f docker-compose.prod.yml run --rm app \
  uv run alembic history --verbose

# Roll back one step
docker compose -f docker-compose.prod.yml run --rm app \
  uv run alembic downgrade -1
```

---

## 12. Scaling considerations

| Concern | Approach |
|---------|----------|
| More request throughput | Increase `--workers` in the `app` command (2 → 4) and bump `cpus` limit |
| More background task throughput | Increase `--concurrency` in the `worker` command, or add a second `worker` container |
| High availability | Move to Docker Swarm or Kubernetes; use managed Postgres (RDS, Supabase) and managed Redis (Elasticache, Upstash) |
| Celery beat HA | Use `celery-redbeat` (Redis-backed scheduler) instead of the default file-based beat to allow safe restarts without duplicate tasks |
| Database connection pool | Add `?pool_size=5&max_overflow=10` to `DATABASE_URL` if the app opens too many connections under load |
