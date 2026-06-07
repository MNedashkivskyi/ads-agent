#!/bin/sh
# Database migration step. Set this as the API service's pre-deploy command:
#   sh scripts/migrate.sh
set -e
alembic -c /app/alembic.ini upgrade head
