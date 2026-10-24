#!/usr/bin/env bash
# One-time setup of ZTB ShiftOrbit on Linux/macOS (local only). Windows: use setup.ps1.
# Usage: ./setup.sh [--dev]   (--dev also installs pytest for running the test suite)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
DEV=0; [[ "${1:-}" == "--dev" ]] && DEV=1

step() { printf '\033[36m==> %s\033[0m\n' "$1"; }

step "Checking Python 3.11 or newer"
PY=""
for c in python3.12 python3.11 python3.13 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
    PY="$c"; break
  fi
done
[[ -n "$PY" ]] || { echo "Python 3.11+ not found. Install it and run setup again." >&2; exit 1; }
echo "    Using $PY ($("$PY" --version))"

step "Checking Node.js 20 or newer"
command -v node >/dev/null || { echo "Node.js not found. Install Node.js 20 LTS or newer." >&2; exit 1; }
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
(( NODE_MAJOR >= 20 )) || { echo "Node.js $(node --version) is too old; need 20+." >&2; exit 1; }
echo "    Node.js $(node --version)"

step "Creating Python virtual environment (backend/.venv)"
[[ -x "$ROOT/backend/.venv/bin/python" ]] || "$PY" -m venv "$ROOT/backend/.venv"
VPY="$ROOT/backend/.venv/bin/python"

step "Installing Python packages"
"$VPY" -m pip install --disable-pip-version-check -q --upgrade pip
REQ=requirements.txt; (( DEV )) && REQ=requirements-dev.txt
"$VPY" -m pip install --disable-pip-version-check -q -r "$ROOT/backend/$REQ"

step "Installing frontend packages and building the web interface"
(cd "$ROOT/frontend" && npm ci --no-audit --no-fund && npm run build)

mkdir -p "$ROOT/data"
step "Checking the installation"
"$VPY" -c 'import ortools, fastapi, sqlalchemy, openpyxl, tzdata; print("    OR-Tools", ortools.__version__)'

printf '\n\033[32mSetup complete.\033[0m Start with ./start.sh, stop with ./stop.sh\n'
