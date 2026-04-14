.PHONY: install fmt lint type test test-all up down migrate migrate-create \
        prod-up prod-down prod-migrate prod-logs \
        db-backup db-restore

install:
	uv sync --all-extras

fmt:
	uv run ruff format adcopilot tests

lint:
	uv run ruff check adcopilot tests

type:
	uv run mypy adcopilot

test:
	uv run --python python pytest tests/ -m "not integration"

test-all:
	uv run --python python pytest tests/

# ── Local development ────────────────────────────────────────────────────────

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run alembic upgrade head

migrate-create:
	uv run alembic revision --autogenerate -m "$(name)"

# ── Production (requires APP_IMAGE, DOMAIN, POSTGRES_PASSWORD in env) ────────

prod-up:
	docker compose -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-migrate:
	docker compose -f docker-compose.prod.yml run --rm app uv run alembic upgrade head

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f --tail=100

# ── Disaster recovery ────────────────────────────────────────────────────────

# Trigger a manual backup right now (requires R2 credentials in .env).
db-backup:
	docker compose exec worker celery -A adcopilot.interfaces.worker.celery_app:celery_app call \
	    adcopilot.interfaces.worker.tasks.nightly_db_backup_task

# Restore a specific backup from R2 to the local Postgres container.
#
#   make db-restore BACKUP=backups/20240101-020000.sql.gz
#   make db-restore BACKUP=20240101-020000.sql.gz     # prefix added automatically
#
# Prerequisites: docker compose up -d postgres, R2 credentials in .env
BACKUP ?=
db-restore:
	@test -n "$(BACKUP)" || (echo "Usage: make db-restore BACKUP=<filename or R2 key>" && exit 1)
	uv run python scripts/db_restore.py "$(BACKUP)"
