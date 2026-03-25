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
export API_PORT="${API_PORT:-8000}"
export MAX_UPLOAD_SIZE_BYTES="${MAX_UPLOAD_SIZE_BYTES:-26214400}"
export POSTGRES_HOST="${LOCAL_POSTGRES_HOST:-localhost}"
export POSTGRES_PORT="${LOCAL_POSTGRES_PORT:-${POSTGRES_PORT:-5432}}"
export POSTGRES_DB="${POSTGRES_DB:-parcelops}"
export POSTGRES_USER="${POSTGRES_USER:-parcelops}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-parcelops}"
export REDIS_HOST="${LOCAL_REDIS_HOST:-localhost}"
export REDIS_PORT="${LOCAL_REDIS_PORT:-${REDIS_PORT:-6379}}"
export LOCAL_STORAGE_ROOT="${LOCAL_STORAGE_ROOT:-$ROOT_DIR/data/uploads}"

if [[ -n "${LOCAL_DATABASE_URL:-}" ]]; then
  export DATABASE_URL="$LOCAL_DATABASE_URL"
else
  export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}"
fi

cd "$ROOT_DIR/apps/api"
./.venv/bin/alembic upgrade head
./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" --reload
