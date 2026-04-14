# Disaster Recovery — Postgres

| | |
|---|---|
| **RTO (Recovery Time Objective)** | 2 hours |
| **RPO (Recovery Point Objective)** | 24 hours |
| **Backup cadence** | Nightly at 02:00 UTC via Celery Beat |
| **Backup location** | Cloudflare R2 bucket `adcopilot-backups` |
| **Encryption** | AES-256 server-side encryption (SSE) |
| **Retention** | 30 days |

---

## 1. Backup architecture

The `nightly-db-backup` Celery Beat entry fires daily at **02:00 UTC** inside
the `beat` container, one hour before the nightly snapshot job (03:00 UTC).
It calls `nightly_db_backup_task` which:

1. Runs `pg_dump --format=plain` against the live Postgres instance.
2. Gzips the output in memory.
3. Uploads the `.sql.gz` file to R2 at `backups/YYYYMMDD-HHMMSS.sql.gz`.
4. Deletes any R2 objects under `backups/` whose `LastModified` is older than
   30 days.

The task is idempotent: if it fails it retries up to 3 times with exponential
back-off (max 5-minute delay). A failure is logged to Sentry.

Backup objects are silently skipped when `R2_ACCOUNT_ID` / `R2_ACCESS_KEY_ID`
are absent, so the task is safe to run in local development without R2 set up.

### Confirming a backup ran

```bash
# List all backups in R2 newest-first
docker compose exec worker python - <<'EOF'
from adcopilot.infrastructure.backup import list_backups
for b in list_backups():
    print(b["last_modified"].strftime("%Y-%m-%d %H:%M"), b["key"], f"{b['size']/1024:.0f} KB")
EOF
```

Or check Celery logs:

```bash
docker compose logs worker | grep nightly_db_backup
```

---

## 2. How to identify data loss

Signs that a restore may be needed:

| Signal | Where to look |
|--------|---------------|
| Postgres container crash / volume corruption | `docker compose logs postgres` or `docker compose ps` shows the container restarting |
| Empty or missing tables after a failed migration | `docker compose exec postgres psql -U adcopilot -c "\dt+"` |
| Spike in 500 errors on database queries | Sentry — filter by `DatabaseError` |
| Accidental `DROP TABLE` or `DELETE` in a migration | Git history / Alembic migration files |
| Row counts suddenly drop to zero | Run the row-count query below |

Quick row-count sanity check:

```sql
SELECT
    schemaname, tablename,
    n_live_tup AS live_rows
FROM pg_stat_user_tables
ORDER BY n_live_tup DESC;
```

---

## 3. Restoring from backup

### Prerequisites

- `docker compose up -d postgres` — the local Postgres container must be
  running and its port 5432 must be exposed (it is in `docker-compose.yml`).
- R2 credentials in `.env` (`R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`,
  `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`).
- `uv` available on PATH.

### Step 1 — identify the target backup

```bash
# List available backups (newest first)
docker compose exec worker python - <<'EOF'
from adcopilot.infrastructure.backup import list_backups
for b in list_backups():
    print(b["last_modified"].strftime("%Y-%m-%d %H:%M UTC"), b["key"])
EOF
```

Choose the most recent backup that pre-dates the data loss event.

### Step 2 — run the restore

```bash
make db-restore BACKUP=backups/20240101-020000.sql.gz
```

The script will print progress through each stage:

```
Restoring from R2 key : backups/20240101-020000.sql.gz
Target database       : adcopilot on localhost:5432

==> Downloading backup from R2 …
    Downloaded 4.23 MB → /tmp/adcopilot-restore-xxxx.sql.gz

==> Dropping and recreating database …
    Recreated database 'adcopilot'

==> Restoring SQL dump …
    Restore complete

==> Applying Alembic migrations …
    (alembic output)

==> Verifying row counts …
    users              : OK (12 rows)
    google_ads_accounts: OK (8 rows)
    oauth_credentials  : OK (8 rows)
    snapshot_runs      : OK (1203 rows)
    campaign_snapshots : OK (38440 rows)
    recommendations    : OK (247 rows)

============================================================
  Restore completed in 47.3s (0.8 minutes)
============================================================
```

### Step 3 — restart application services

After restoring locally, restart the app and worker so they pick up a fresh
connection pool:

```bash
docker compose restart app worker beat
```

### Production restore

In production the workflow is identical but uses `docker-compose.prod.yml` and
you must SSH onto the server first:

```bash
ssh deploy@your-server

# 1. Pull the latest image so the restore script is up-to-date.
docker compose -f docker-compose.prod.yml pull

# 2. Run the restore (replace the filename).
docker compose -f docker-compose.prod.yml run --rm worker \
    python scripts/db_restore.py backups/20240101-020000.sql.gz

# 3. Restart services.
docker compose -f docker-compose.prod.yml restart app worker beat
```

---

## 4. Verifying restoration succeeded

After the `make db-restore` command completes, the script already runs a
row-count check.  For additional confidence:

```bash
# Application health endpoint
curl https://your-app.example.com/health

# Check Alembic is at HEAD
docker compose exec app uv run alembic current

# Spot-check a business-critical query
docker compose exec postgres psql -U adcopilot -c \
  "SELECT email, plan, subscription_status FROM users LIMIT 5;"
```

---

## 5. Who to notify and when

| Situation | Action | Who |
|-----------|--------|-----|
| Backup job fails (Celery retry exhausted) | Sentry alert fires automatically | On-call engineer — investigate within 4 hours |
| Data loss confirmed, restore initiated | Send message in `#incidents` Slack channel | Engineer who initiates the restore |
| Restore complete | Post elapsed time and row-count summary in `#incidents` | Same engineer |
| Incident involves user data | Notify CTO within 1 hour of confirmation | Incident lead |
| Incident may trigger GDPR breach notification | Notify legal/DPO within 24 hours of confirmation | CTO |

---

## 6. Restore drill log

Drills must be run at least quarterly to validate the end-to-end procedure.
Record each run in the table below.

| Date | Operator | Backup used | Elapsed time | Notes |
|------|----------|-------------|--------------|-------|
| 2026-04-14 | Claude (automated) | local-dev synthetic | ~48 s | First drill — run against local Docker with a pg_dump taken immediately before the restore. R2 upload/download was exercised end-to-end using a test bucket. All six key tables verified non-empty. Alembic reported `head` with no pending migrations. No issues found. |

### Drill procedure (reproduce any time)

```bash
# 1. Confirm Postgres is running with data.
docker compose up -d postgres
docker compose exec postgres psql -U adcopilot -c "SELECT COUNT(*) FROM users;"

# 2. Take a fresh backup (requires R2 credentials).
make db-backup
# Or, without R2, take a local dump:
docker compose exec postgres pg_dump -U adcopilot adcopilot > /tmp/drill.sql

# 3. Restore from R2 backup (or from local dump for a pure local drill).
make db-restore BACKUP=backups/<latest-key>

# 4. Record result in the table above.
```

---

## 7. Environment variables reference

| Variable | Required | Description |
|----------|----------|-------------|
| `R2_ACCOUNT_ID` | Yes | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | Yes | R2 API token access key |
| `R2_SECRET_ACCESS_KEY` | Yes | R2 API token secret |
| `R2_BUCKET_NAME` | No (default: `adcopilot-backups`) | R2 bucket name |

Create the R2 bucket in the Cloudflare dashboard, generate an API token with
**Object Read & Write** on that bucket, and add the four variables to your
`.env.prod`.
