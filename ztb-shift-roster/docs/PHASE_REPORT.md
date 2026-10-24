# Phase report

Environment: Linux cloud container, Python 3.11.17 venv, Node 22.22, Chromium for Playwright.
**Not Windows.** Phase 8 (local UAT) is pending and must be done by ZTB.

Final test evidence (last full run):

| Suite | Result |
|---|---|
| Backend pytest (`backend/tests`, 10 files) | **73 passed**, 0 failed (~60 s) |
| Frontend Vitest | **20 passed** |
| TypeScript `tsc -b` | clean |
| Playwright E2E (desktop + mobile, real backend + built UI, temp DB) | **8 passed** |
| Linux/macOS `setup.sh` / `start.sh` / `stop.sh` from a fresh GitHub clone | setup, start, double-start, stop, restart with data kept: all work |
| Exploratory UI pass (30 actions across every page, real solver) | 30/30 passed, no console errors, no server errors |
| Windows `.ps1` scripts | **not executed** (no PowerShell in the build environment) |

## Phase 1: Foundations ✅
Settings (loopback-only), SQLite engine (FK, WAL), all ORM models, schema version check,
seeding of the default policy and code mappings, security middleware (Host, Origin,
CSRF header, body size, security headers), health endpoint, test harness.
Files: `backend/app/{config,db,security,main}.py`, `app/models/*`, `services/{seed,audit,jobs}.py`.
Tests: `test_foundation.py`, `test_security.py` (14).

## Phase 2: Project and analyst management ✅
CRUD APIs with strict validation for:
- projects, shift templates (overnight-aware durations, reserved codes), staffing
  (all days / weekday / date)
- skills, analysts with multi-project eligibility, allowed shifts and preferences
- policies (single default), availability exceptions, holidays, shift-code mappings

Deleting records used by published or historical rosters is refused.
Files: `app/api/{organization,analysts,settings}.py`, `app/schemas/*`. Tests: `test_management_api.py` (8).
UI delivered in phase 5.

## Phase 3: Scheduling engine and independent validator ✅
- Plain-data problem (`domain.py`) with the rule semantics documented.
- Candidate generation, and the CP-SAT model covering all 12 hard rules and 6 soft objectives.
- Statuses: OPTIMAL, FEASIBLE, INFEASIBLE, TIMEOUT, CANCELLED, ERROR.
- Assumption-based infeasibility cores; a preliminary check (shortages, per-day matching,
  weekly capacity, locks).
- Asynchronous jobs with real progress and cancellation.
- An independent validator, which also gates saving solver output.
- Roster versions, validated edits with override reasons, publish/clone/delete.

Bugs found and fixed during the phase:
1. Month-boundary history was treated as globally known; it is now per analyst, with an
   explicit inherited-week warning.
2. Cancelling before CP-SAT started was ignored; a watcher thread now stops the search.

Files: `app/solver/*`, `app/validators/*`, `services/{problem_builder,roster_service}.py`, `api/rosters.py`.
Tests: `test_solver.py` (20), `test_roster_api.py` (8).

## Phase 4: Leave and regeneration ✅
- Leave lifecycle: submit, edit (approved → pending again), approve, reject, cancel, partial day, overlap protection.
- Impact assessment that treats pending leave as approved in memory only.
- Replacement suggestions ranked by added violations, then workload.
- Leave-window regeneration (simulate or create a draft), with everything outside the window locked and verified.

Files: `services/leave_service.py`, `api/leaves.py`. Tests: `test_leave_api.py` (2 broad scenario tests).

## Phase 5: Calendar and dashboard ✅
- React + TS + Vite + Tailwind 4 + shadcn/ui (Radix) + React Query + RHF/Zod + FullCalendar,
  in a navy/blue ZTB theme. Responsive layout with a mobile drawer.
- Pages: dashboard, the 10-step generator wizard, the roster editor, leave, analysts,
  projects & shifts, import/export, settings & data.
- Roster editor:
  - monthly matrix, shift view, week and month calendars
  - project, analyst and shift filters
  - drag-and-drop, cell editor, locks, undo/redo, conflict highlighting, leave and week-off markers
  - draft/published versions
- Dashboard API. Admin API (backup, restore, delete-all, synthetic demo data, audit), pulled
  forward because the Settings UI needs it.

Files: `frontend/src/**`, `backend/app/api/{dashboard,admin}.py`, `services/{backup,demo}.py`.
Tests: Vitest (20), `test_dashboard.py` (1), `test_admin.py` (5).

## Phase 6: Excel ✅
- 7-sheet XLSX export: Excel tables, frozen headers, filters, shift colours, formula-injection guard.
- XLSX/CSV import: in-memory preview, header detection, column-mapping suggestions,
  all-or-nothing validation. Covers analysts, leave and rosters, including the previous SOC
  layout through configurable code mappings.
- Import templates; synthetic fixtures and their generator script.

Files: `services/excel_{common,export,import}.py`, `api/imports.py`, `scripts/make_synthetic_fixtures.py`, `sample-data/*`.
Tests: `test_excel.py` (8), including an exact export → import round trip.

## Phase 7: Security hardening and automated testing ✅ (with gaps noted)
- A route-wide CSRF/Origin test over every write endpoint.
- Tests for SQL metacharacters, SPA path traversal, error leakage and log hygiene.
- API docs page made opt-in (it loads CDN assets).
- Playwright E2E suite covering the primary workflow. It **found a real bug**: undo history
  was reset on every render, so undo never worked. Fixed.
- Windows scripts, test runners and the documentation set.

Gap: the PowerShell scripts were never executed.
Files: `tests/test_security_hardening.py` (6), `frontend/e2e/*`, `playwright.config.ts`, `*.ps1`, `scripts/*`, `docs/*`.

## Phase 8: Local UAT ⏳ not started (requires Windows)
Use `docs/UAT_CHECKLIST.md`. The real August 2026 roster has not been supplied; the
historical adapter is tested only with synthetic data.

## Incomplete or deferred (see KNOWN_ISSUES.md)
- Windows execution of the scripts and app; real historical file; D/AN timings.
- No authentication or multi-user support (by design for a local app); no DB migrations;
  no leave balances or notifications.

## Local-run verification (after phase 7)

Steps:
- Fresh clone from GitHub, clean install with `requirements.txt` only.
- Backend suite run under Python 3.11 and 3.13 (73 and 72 tests at the time, all passing);
  setup also succeeded with Python 3.12.
- Scripted walkthrough of 30 user actions on a running instance.

Fixed during this pass:
1. Infeasibility explanations were shown as raw JSON. They are now plain sentences.
2. A new pre-solve check catches "required days × shift length > weekly hours cap"
   (e.g. a 40 h analyst under the exact 5 × 9 h week).
3. *Assign* on a replacement suggestion that breaks a rule failed with a bare error. It now
   uses the same "list the violations, give a reason or cancel" confirmation as the editor.
4. The cell editor offered the shift already in the cell, which caused an "already exists"
   error. That shift is now hidden.
5. `start.sh` recorded the wrong PID, so `stop.sh` left the server running. Fixed and re-tested.
