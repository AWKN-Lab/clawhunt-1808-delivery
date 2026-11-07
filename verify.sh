#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="python3"
fi
export PYTHONPATH="$ROOT"
cd "$ROOT"

failed=0
step() {
  local name="$1"
  shift
  echo
  echo "=== $name ==="
  "$@"
  local code=$?
  if [ $code -ne 0 ]; then
    echo "STEP FAIL: $name (exit $code)"
    failed=1
  else
    echo "STEP PASS: $name"
  fi
}

step "pytest" "$PYTHON" -m pytest -q
step "eval (fail-closed thresholds)" "$PYTHON" -m eval.run
step "compose static check" "$PYTHON" scripts/compose_check.py
step "http smoke (7/7 booking + SSE latency)" "$PYTHON" scripts/http_smoke.py

if [ $failed -eq 0 ]; then
  echo
  echo "VERIFY PASS"
else
  echo
  echo "VERIFY FAIL"
fi
exit $failed
