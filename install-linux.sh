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
SYSTEM_BIN="/usr/local/bin/hashsight"
PYTHON_BIN_EXPLICIT=0

show_help() {
  cat <<'EOF'
HashSight Linux installer

Options:
  --with-apt          Install Python prerequisites using apt first
  --python <binary>   Python executable to use (default: python3)
  --venv <dir>        Virtualenv path (default: .venv)
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing command: $1" >&2
    exit 1
  fi
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --with-apt)
        WITH_APT=1
        shift
        ;;
      --python)
        PYTHON_BIN="${2:-}"
        PYTHON_BIN_EXPLICIT=1
        shift 2
        ;;
      --venv)
        VENV_DIR="${2:-}"
        shift 2
        ;;
      -h|--help)
        show_help
        exit 0
        ;;
      *)
        echo "Unknown option: $1" >&2
        exit 2
        ;;
    esac
  done
}

bootstrap_apt_if_requested() {
  if [[ $WITH_APT -ne 1 ]]; then
    return
  fi

  require_cmd apt-get
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y --no-install-recommends \
    ca-certificates \
    python3.11 \
    python3.11-venv \
    python3-pip

  # When apt bootstrap is used and caller did not pin --python, prefer 3.11 explicitly.
  if [[ $PYTHON_BIN_EXPLICIT -eq 0 ]]; then
    PYTHON_BIN="python3.11"
  fi
}

verify_python_version() {
  "$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    print("HashSight requires Python >= 3.11. Detected:", sys.version.split()[0])
    raise SystemExit(1)
print("Python version OK:", sys.version.split()[0])
PY
}

resolve_venv_abs() {
  local install_root
  install_root="$(pwd -P)"
  if [[ "$VENV_DIR" = /* ]]; then
    VENV_ABS="$VENV_DIR"
  else
    VENV_ABS="$install_root/$VENV_DIR"
  fi
}

install_hashsight() {
  "$PYTHON_BIN" -m venv "$VENV_DIR"
  # shellcheck disable=SC1090
  source "$VENV_DIR/bin/activate"

  python -m pip install --upgrade pip setuptools wheel
  python -m pip install -e .
  hash -r

  HASHSIGHT_BIN="$VENV_ABS/bin/hashsight"
  if [[ ! -x "$HASHSIGHT_BIN" ]]; then
    echo "Install finished but expected executable was not found: $HASHSIGHT_BIN" >&2
    exit 1
  fi
}

resolve_target_home() {
  TARGET_USER="${SUDO_USER:-${USER}}"
  TARGET_HOME="$HOME"

  if command -v getent >/dev/null 2>&1; then
    local target_home_from_db
    target_home_from_db="$(getent passwd "$TARGET_USER" | cut -d: -f6 || true)"
    if [[ -n "$target_home_from_db" ]]; then
      TARGET_HOME="$target_home_from_db"
    fi
  fi
}

write_launcher() {
  local launcher_path
  launcher_path="$1"
  cat > "$launcher_path" <<EOF
#!/usr/bin/env bash
exec "$HASHSIGHT_BIN" "\$@"
EOF
  chmod +x "$launcher_path"
}

install_launchers() {
  USER_BIN_DIR="${TARGET_HOME}/.local/bin"
  USER_LAUNCHER="$USER_BIN_DIR/hashsight"

  mkdir -p "$USER_BIN_DIR"
  write_launcher "$USER_LAUNCHER"

  SYSTEM_LAUNCHER=""
  if [[ -w "/usr/local/bin" ]]; then
    SYSTEM_LAUNCHER="$SYSTEM_BIN"
    write_launcher "$SYSTEM_LAUNCHER"
  fi
}

show_path_help_if_needed() {
  if command -v hashsight >/dev/null 2>&1; then
    hashsight --help >/dev/null
    return
  fi

  echo "HashSight installed, but 'hashsight' is not currently on your PATH." >&2
  echo "You can run it right now with:" >&2
  echo "  ${USER_LAUNCHER} --help" >&2
  if [[ -n "$SYSTEM_LAUNCHER" ]]; then
    echo "A system launcher was installed at: $SYSTEM_LAUNCHER" >&2
  fi
  echo >&2
  echo "To make 'hashsight' available in new shells, add this line to your profile:" >&2
  echo "  export PATH=\"${USER_BIN_DIR}:\$PATH\"" >&2
  echo "Then reload your shell and run: hashsight --help" >&2
}

print_summary() {
  echo "HashSight installed successfully."
  echo "Virtualenv: $VENV_DIR"
  echo "Launcher: $USER_LAUNCHER"
  if [[ -n "$SYSTEM_LAUNCHER" ]]; then
    echo "System launcher: $SYSTEM_LAUNCHER"
  fi
  if command -v hashsight >/dev/null 2>&1; then
    echo "Command: $(command -v hashsight)"
  fi
}

parse_args "$@"
bootstrap_apt_if_requested
require_cmd "$PYTHON_BIN"
resolve_venv_abs
verify_python_version
install_hashsight
resolve_target_home
install_launchers
show_path_help_if_needed
print_summary
