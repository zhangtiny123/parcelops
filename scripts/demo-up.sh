#!/usr/bin/env zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT_DIR/.env.example" "$ENV_FILE"
  echo "Created .env from .env.example"
fi

set -a
source "$ENV_FILE"
set +a

WEB_PORT="${WEB_PORT:-3000}"
API_PORT="${API_PORT:-8000}"

cd "$ROOT_DIR"

echo "==> Generating seeded demo dataset"
python3 scripts/generate_demo_dataset.py --output-dir "$ROOT_DIR/data/generated"

echo "==> Starting Docker Compose stack"
docker compose up --build -d

echo "==> Loading the seeded demo workflow"
python3 scripts/seed_demo_workflow.py \
  --api-base-url "http://localhost:${API_PORT}" \
  --dataset-dir "$ROOT_DIR/data/generated" \
  --wait-for-api

echo
echo "Demo ready:"
echo "- Web: http://localhost:${WEB_PORT}"
echo "- API docs: http://localhost:${API_PORT}/docs"
echo "- Reset with: docker compose down -v"
