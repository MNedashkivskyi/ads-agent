#!/bin/sh
# API service entrypoint (Railway). Uses start.sh at repo root.
set -e
exec uvicorn adcopilot.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 2 --proxy-headers
