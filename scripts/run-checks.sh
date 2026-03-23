#!/usr/bin/env zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

for node_bin_dir in "$ROOT_DIR"/.tools/node-*/bin; do
  if [[ -d "$node_bin_dir" ]]; then
    export PATH="$node_bin_dir:$PATH"
    break
  fi
done

echo "==> API: format check"
cd "$ROOT_DIR/apps/api"
./.venv/bin/ruff format --check .

echo "==> API: lint"
./.venv/bin/ruff check .

echo "==> API: tests"
./.venv/bin/pytest -q

echo "==> Web: typecheck"
cd "$ROOT_DIR/apps/web"
npm run typecheck

echo "==> Web: lint"
npm run lint
