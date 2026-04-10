# AdCopilot

Google Ads Co-Pilot — AI-powered ad management assistant.

## Stack

- Python 3.12, FastAPI, PostgreSQL 16, SQLAlchemy 2.x async, Alembic
- Celery + Redis for background tasks
- python-telegram-bot for Telegram integration
- google-ads-python for Google Ads API
- pydantic-settings for configuration
- structlog for structured logging

## Setup

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker & Docker Compose

### Local development

```bash
# Install dependencies
make install

# Copy and edit environment variables
cp .env.example .env

# Start infrastructure (Postgres + Redis)
make up

# Run database migrations
make migrate

# Start the API server
uv run uvicorn adcopilot.main:app --reload
```

### Running tests

```bash
# Unit tests only (no DB required)
make test

# All tests including integration (requires running Postgres)
TEST_DATABASE_URL=postgresql+asyncpg://adcopilot:adcopilot@localhost:5432/adcopilot_test make test-all
```

### Code quality

```bash
make fmt       # Format code with ruff
make lint      # Lint with ruff
make type      # Type-check with mypy
```

### Docker

```bash
make up    # Start all services
make down  # Stop all services
```

## Architecture

Hexagonal / ports & adapters:

```
adcopilot/
  domain/           # Pure dataclasses + value objects, no framework imports
  application/      # Use cases and port protocols
  infrastructure/   # DB, Google Ads, Telegram, LLM adapters
  interfaces/       # FastAPI routes, Celery tasks, Telegram bot entrypoint
  config.py         # pydantic-settings
  main.py           # FastAPI app factory
```

## Environment variables

See `.env.example` for all required and optional variables.

### Telegram bot setup

1. Create a bot via [@BotFather](https://t.me/BotFather) and copy the token
2. Set `TELEGRAM_BOT_TOKEN=<token>` in `.env`
3. Run the one-time configuration script to register commands and descriptions:
   ```bash
   python scripts/setup_telegram_bot.py
   ```
4. Run the bot locally in polling mode:
   ```bash
   python scripts/run_bot.py
   ```

### Google Ads setup

To use Google Ads integration:
1. Create a Google Cloud project and enable the Google Ads API
2. Create OAuth 2.0 credentials (web application type)
3. Apply for a Google Ads developer token
4. Set `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_CLIENT_ID`, `GOOGLE_ADS_CLIENT_SECRET` in `.env`

Integration tests requiring Google Ads credentials are skipped in CI if the env vars are not set.
