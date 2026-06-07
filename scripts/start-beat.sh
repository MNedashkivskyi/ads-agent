#!/bin/sh
# Celery BEAT service entrypoint (Railway). Set this as the beat service's
# start command:  sh scripts/start-beat.sh
# IMPORTANT: run EXACTLY ONE beat instance — duplicates double-fire every job.
set -e
exec celery -A adcopilot.interfaces.worker.celery_app:celery_app beat \
    --loglevel=warning --schedule /tmp/celerybeat-schedule
