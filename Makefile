.PHONY: install fmt lint type test test-all up down migrate migrate-create \
        prod-up prod-down prod-migrate prod-logs

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
