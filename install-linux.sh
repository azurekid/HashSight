#!/usr/bin/env bash
set -euo pipefail

# HashSight Linux installer with optional apt bootstrap.
# Usage:
#   ./install-linux.sh
#   ./install-linux.sh --with-apt
#   ./install-linux.sh --python python3.11 --venv .venv

WITH_APT=0
PYTHON_BIN="python3"
VENV_DIR=".venv"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-apt)
      WITH_APT=1
      shift
      ;;
    --python)
      PYTHON_BIN="${2:-}"
      shift 2
      ;;
    --venv)
      VENV_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
HashSight Linux installer

Options:
  --with-apt          Install Python prerequisites using apt first
  --python <binary>   Python executable to use (default: python3)
  --venv <dir>        Virtualenv path (default: .venv)
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1" >&2
    exit 1
  fi
}

if [[ $WITH_APT -eq 1 ]]; then
  require_cmd apt-get
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-venv \
    python3-pip
fi

require_cmd "$PYTHON_BIN"

# Enforce project minimum supported Python version from pyproject.toml.
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 8):
    print("HashSight requires Python >= 3.8. Detected:", sys.version.split()[0])
    raise SystemExit(1)
print("Python version OK:", sys.version.split()[0])
PY

"$PYTHON_BIN" -m venv "$VENV_DIR"
# shellcheck disable=SC1090
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
hash -r

if ! command -v hashsight >/dev/null 2>&1; then
  echo "Install finished but hashsight not on PATH; try: source $VENV_DIR/bin/activate" >&2
  exit 1
fi

hashsight --help >/dev/null

echo "HashSight installed successfully."
echo "Virtualenv: $VENV_DIR"
echo "Command: $(command -v hashsight)"
