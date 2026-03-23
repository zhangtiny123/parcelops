#!/usr/bin/env zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

export APP_ENV="${APP_ENV:-development}"
export REDIS_HOST="${REDIS_HOST:-localhost}"
export REDIS_PORT="${REDIS_PORT:-6381}"
export REDIS_BROKER_DB="${REDIS_BROKER_DB:-0}"
export REDIS_RESULT_DB="${REDIS_RESULT_DB:-1}"
export LOCAL_STORAGE_ROOT="${LOCAL_STORAGE_ROOT:-$ROOT_DIR/data/uploads}"

if [[ -z "${CELERY_BROKER_URL:-}" ]]; then
  export CELERY_BROKER_URL="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_BROKER_DB}"
fi

if [[ -z "${CELERY_RESULT_BACKEND:-}" ]]; then
  export CELERY_RESULT_BACKEND="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_RESULT_DB}"
fi

cd "$ROOT_DIR/apps/worker"
./.venv/bin/celery -A worker_app worker --loglevel=INFO
