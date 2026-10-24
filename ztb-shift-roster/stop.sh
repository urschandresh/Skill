#!/usr/bin/env bash
# Stop ZTB ShiftOrbit started by start.sh. Data stays in the data folder.
set -euo pipefail
RUN="$(cd "$(dirname "$0")" && pwd)/.run"
if [[ -f "$RUN/backend.pid" ]] && kill -0 "$(cat "$RUN/backend.pid")" 2>/dev/null; then
  PID="$(cat "$RUN/backend.pid")"
  kill "$PID"
  for _ in $(seq 1 20); do kill -0 "$PID" 2>/dev/null || break; sleep 0.5; done
  kill -0 "$PID" 2>/dev/null && kill -9 "$PID"
  echo "ZTB ShiftOrbit stopped (PID $PID)."
else
  echo "ShiftOrbit was not running."
fi
rm -f "$RUN/backend.pid"
