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
COPY adcopilot ./adcopilot

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

CMD ["uvicorn", "adcopilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
