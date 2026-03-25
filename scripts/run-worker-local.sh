#!/usr/bin/env zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

export APP_ENV="${APP_ENV:-development}"
export DATABASE_ECHO="${DATABASE_ECHO:-0}"
export POSTGRES_HOST="${LOCAL_POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${LOCAL_POSTGRES_PORT:-${POSTGRES_PORT:-5432}}"
export POSTGRES_DB="${POSTGRES_DB:-parcelops}"
export POSTGRES_USER="${POSTGRES_USER:-parcelops}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-parcelops}"
export REDIS_HOST="${LOCAL_REDIS_HOST:-localhost}"
export REDIS_PORT="${LOCAL_REDIS_PORT:-${REDIS_PORT:-6379}}"
export REDIS_BROKER_DB="${REDIS_BROKER_DB:-0}"
export REDIS_RESULT_DB="${REDIS_RESULT_DB:-1}"
export LOCAL_STORAGE_ROOT="${LOCAL_STORAGE_ROOT:-$ROOT_DIR/data/uploads}"

if [[ -n "${LOCAL_DATABASE_URL:-}" ]]; then
  export DATABASE_URL="$LOCAL_DATABASE_URL"
else
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi

if [[ -n "${LOCAL_CELERY_BROKER_URL:-}" ]]; then
  export CELERY_BROKER_URL="$LOCAL_CELERY_BROKER_URL"
else
  export CELERY_BROKER_URL="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_BROKER_DB}"
fi

if [[ -n "${LOCAL_CELERY_RESULT_BACKEND:-}" ]]; then
  export CELERY_RESULT_BACKEND="$LOCAL_CELERY_RESULT_BACKEND"
else
  export CELERY_RESULT_BACKEND="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_RESULT_DB}"
fi

export PYTHONPATH="$ROOT_DIR/apps/api:$ROOT_DIR/apps/worker${PYTHONPATH:+:$PYTHONPATH}"

cd "$ROOT_DIR/apps/worker"
./.venv/bin/celery -A worker_app worker --loglevel=INFO
