#!/usr/bin/env bash
# Start ZTB ShiftOrbit on this computer only. Usage: ./start.sh [port]   (default 8000)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
PORT="${1:-${ZTB_PORT:-8000}}"
RUN="$ROOT/.run"
VPY="$ROOT/backend/.venv/bin/python"
mkdir -p "$RUN"

[[ -x "$VPY" ]] || { echo "Not set up yet. Run ./setup.sh first." >&2; exit 1; }
[[ -f "$ROOT/frontend/dist/index.html" ]] || { echo "Web interface not built. Run ./setup.sh." >&2; exit 1; }

if [[ -f "$RUN/backend.pid" ]] && kill -0 "$(cat "$RUN/backend.pid")" 2>/dev/null; then
  echo "ShiftOrbit is already running (PID $(cat "$RUN/backend.pid"))."
  exit 0
fi

(cd "$ROOT/backend" && ZTB_HOST=127.0.0.1 ZTB_PORT="$PORT" nohup "$VPY" run.py \
  >"$RUN/backend.log" 2>"$RUN/backend.err.log" & echo $! >"$RUN/backend.pid")

for _ in $(seq 1 60); do
  sleep 1
  if ! kill -0 "$(cat "$RUN/backend.pid")" 2>/dev/null; then break; fi
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
    printf '\033[32mZTB ShiftOrbit is running at http://127.0.0.1:%s (this computer only).\033[0m\n' "$PORT"
    echo "Stop it with ./stop.sh"
    exit 0
  fi
done
echo "Backend did not start. Last log lines:" >&2
tail -n 20 "$RUN/backend.err.log" >&2 || true
rm -f "$RUN/backend.pid"
exit 1
