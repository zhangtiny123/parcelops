#!/usr/bin/env zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

export APP_ENV="${APP_ENV:-development}"
export DATABASE_ECHO="${DATABASE_ECHO:-0}"
export POSTGRES_HOST="${POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${POSTGRES_PORT:-5433}"
export POSTGRES_DB="${POSTGRES_DB:-parcelops}"
export POSTGRES_USER="${POSTGRES_USER:-parcelops}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-parcelops}"
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6381}"
export REDIS_BROKER_DB="${REDIS_BROKER_DB:-0}"
export REDIS_RESULT_DB="${REDIS_RESULT_DB:-1}"
export LOCAL_STORAGE_ROOT="${LOCAL_STORAGE_ROOT:-$ROOT_DIR/data/uploads}"

if [[ -z "${DATABASE_URL:-}" ]]; then
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi

if [[ -z "${CELERY_BROKER_URL:-}" ]]; then
  export CELERY_BROKER_URL="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_BROKER_DB}"
fi

if [[ -z "${CELERY_RESULT_BACKEND:-}" ]]; then
  export CELERY_RESULT_BACKEND="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_RESULT_DB}"
fi

export PYTHONPATH="$ROOT_DIR/apps/api:$ROOT_DIR/apps/worker${PYTHONPATH:+:$PYTHONPATH}"

cd "$ROOT_DIR/apps/worker"
./.venv/bin/celery -A worker_app worker --loglevel=INFO
