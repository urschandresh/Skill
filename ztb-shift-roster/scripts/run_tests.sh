#!/usr/bin/env bash
# Run every automated test suite (Linux/macOS). Set PW_CHROMIUM to reuse an installed Chromium.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
(cd "$ROOT/backend" && .venv/bin/python -m pytest)
cd "$ROOT/frontend"
npm run typecheck
npm test
if [[ "${SKIP_E2E:-0}" != "1" ]]; then
  npm run build
  npx playwright test
fi
echo "All test suites passed."
