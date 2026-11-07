#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8000}"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi
export PYTHONPATH="$ROOT"
export DB_MODE="sqlite"
export LLM_MODE="mock"
cd "$ROOT"
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
