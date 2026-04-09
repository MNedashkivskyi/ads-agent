.PHONY: install fmt lint type test test-all up down migrate migrate-create

install:
	uv sync --all-extras

fmt:
	uv run ruff format adcopilot tests

lint:
	uv run ruff check adcopilot tests

type:
	uv run mypy adcopilot

test:
	uv run pytest tests/ -m "not integration"

test-all:
	uv run pytest tests/

up:
	docker compose up -d

down:
	docker compose down

migrate:
	uv run alembic upgrade head

migrate-create:
	uv run alembic revision --autogenerate -m "$(name)"
