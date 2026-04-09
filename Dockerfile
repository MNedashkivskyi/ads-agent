FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install uv

COPY pyproject.toml ./
RUN uv sync --no-dev --no-install-project

FROM python:3.12-slim AS runtime

WORKDIR /app

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

COPY --from=builder /app/.venv /app/.venv
COPY adcopilot ./adcopilot

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

USER appuser

EXPOSE 8000

CMD ["uvicorn", "adcopilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
