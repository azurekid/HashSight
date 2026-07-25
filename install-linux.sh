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
SYSTEM_BIN_FALLBACK="/usr/bin/hashsight"
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

warn() {
  echo "WARNING: $*" >&2
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
  if ! apt-get update; then
    warn "apt-get update failed; continuing without apt bootstrap."
    warn "Detected apt metadata/signature issues can cause this (for example NO_PUBKEY or 404 errors)."
    warn "Fix apt repositories, then rerun with --with-apt if you want automatic dependency installation."
    return
  fi

  if ! apt-get install -y --no-install-recommends \
    ca-certificates \
    python3 \
    python3-venv \
    python3-pip; then
    warn "apt install failed; continuing with currently available Python tooling."
    warn "If virtualenv creation later fails, install package: python3-venv"
  fi

  # When apt bootstrap is used and caller did not pin --python, use distro default python3.
  if [[ $PYTHON_BIN_EXPLICIT -eq 0 ]]; then
    PYTHON_BIN="python3"
  fi
}

pick_python_if_needed() {
  if [[ $PYTHON_BIN_EXPLICIT -eq 1 ]]; then
    return
  fi

  local candidates=(python3 python3.13 python3.12 python3.11)
  local candidate
  for candidate in "${candidates[@]}"; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi

    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
    then
      PYTHON_BIN="$candidate"
      return
    fi
  done
}

verify_python_version() {
  "$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    print("HashSight requires Python >= 3.11. Detected:", sys.version.split()[0])
    print("Install a newer Python and rerun, or pass --python <path-to-python>=3.11+.")
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
  if ! "$PYTHON_BIN" -m venv "$VENV_DIR"; then
    echo "Failed to create virtual environment with $PYTHON_BIN." >&2
    echo "Install venv support (for apt-based distros: python3-venv) and retry." >&2
    exit 1
  fi
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
  mkdir -p "$(dirname "$launcher_path")"
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
  if [[ $EUID -eq 0 ]]; then
    if write_launcher "$SYSTEM_BIN"; then
      SYSTEM_LAUNCHER="$SYSTEM_BIN"
    elif write_launcher "$SYSTEM_BIN_FALLBACK"; then
      SYSTEM_LAUNCHER="$SYSTEM_BIN_FALLBACK"
    fi
  elif [[ -d "$(dirname "$SYSTEM_BIN")" && -w "$(dirname "$SYSTEM_BIN")" ]]; then
    if write_launcher "$SYSTEM_BIN"; then
      SYSTEM_LAUNCHER="$SYSTEM_BIN"
    fi
  fi
}

show_path_help_if_needed() {
  if command -v hashsight >/dev/null 2>&1; then
    hashsight --help >/dev/null
    return
  fi

  echo "HashSight installed, but 'hashsight' is not currently on your PATH." >&2
  echo "You can run it right now with:" >&2
  if [[ -n "$SYSTEM_LAUNCHER" ]]; then
    echo "  ${SYSTEM_LAUNCHER} --help" >&2
  else
    echo "  ${USER_LAUNCHER} --help" >&2
  fi
  if [[ -n "$SYSTEM_LAUNCHER" ]]; then
    echo "A system launcher was installed at: $SYSTEM_LAUNCHER" >&2
  fi
  echo >&2
  echo "To make 'hashsight' available in new shells, add this line to your profile:" >&2
  echo "  export PATH=\"${USER_BIN_DIR}:\$PATH\"" >&2
  echo "Then reload your shell and run: hashsight --help" >&2
}

print_shell_refresh_hint() {
  echo
  echo "If your shell still says 'command not found', refresh command lookup:"
  echo "  bash/sh: hash -r"
  echo "  zsh: rehash"
  echo "  or start a new login shell: exec \"\$SHELL\" -l"
}

verify_launchers() {
  if [[ ! -x "$USER_LAUNCHER" ]]; then
    echo "Expected user launcher missing or not executable: $USER_LAUNCHER" >&2
    exit 1
  fi

  if [[ -n "$SYSTEM_LAUNCHER" && ! -x "$SYSTEM_LAUNCHER" ]]; then
    echo "Expected system launcher missing or not executable: $SYSTEM_LAUNCHER" >&2
    exit 1
  fi
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
  print_shell_refresh_hint
}

parse_args "$@"
bootstrap_apt_if_requested
pick_python_if_needed
require_cmd "$PYTHON_BIN"
resolve_venv_abs
verify_python_version
install_hashsight
resolve_target_home
install_launchers
verify_launchers
show_path_help_if_needed
print_summary
