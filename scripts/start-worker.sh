#!/bin/sh
# Celery WORKER service entrypoint (Railway). Set this as the worker service's
# start command:  sh scripts/start-worker.sh
set -e
exec celery -A adcopilot.interfaces.worker.celery_app:celery_app worker \
    --loglevel=warning -Q default --concurrency=4 --max-tasks-per-child=200
