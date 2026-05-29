FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

FROM python:3.12-slim AS runtime

WORKDIR /app

# postgresql-client provides pg_dump, needed by the Celery backup task.
RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system appgroup && adduser --system --ingroup appgroup --no-create-home appuser

COPY --from=builder /app/.venv /app/.venv
COPY alembic.ini ./
COPY start.sh ./
COPY adcopilot ./adcopilot
# Vertical templates and prompt files used at runtime by the launch flow
# (YamlVerticalTemplateAdapter, website_intelligence, etc.).  Without this
# COPY the production image logs "verticals_dir_missing" and falls back to
# zero categories on Step 1 of the campaign wizard.
COPY config ./config

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN chmod +x /app/start.sh

USER appuser

EXPOSE 8000

CMD ["/app/start.sh"]
