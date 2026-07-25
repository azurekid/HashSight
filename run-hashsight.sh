#!/usr/bin/env bash
set -euo pipefail

# One-command launcher for HashSight.
# Runs directly from source without pip/venv installation.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

ensure_python() {
  if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "Error: $PYTHON_BIN not found. Install Python 3.9+ first." >&2
    exit 1
  fi

  "$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 9):
    print(f"Error: HashSight requires Python >= 3.9, found {sys.version.split()[0]}")
    raise SystemExit(1)
PY
}

main() {
  ensure_python

  if [[ $# -eq 0 ]]; then
    exec "$PYTHON_BIN" -m hashsight.cli --help
  fi

  cd "$ROOT_DIR"
  exec "$PYTHON_BIN" -m hashsight.cli "$@"
}

main "$@"
