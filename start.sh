#!/bin/sh
# Entrypoint for the API service on Railway.
# Railway injects $PORT dynamically — this script ensures the shell expands it
# before exec-ing uvicorn (no quoting or glob-expansion issues).
set -e
exec uvicorn adcopilot.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 2 \
    --proxy-headers
