#!/usr/bin/env zsh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$ROOT_DIR/apps/api"
./.venv/bin/python -m app.copilot.eval_cli "$@"
