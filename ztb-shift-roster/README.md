# ZTB ShiftOrbit

Local-first automatic shift roster maker for the SOC teams of **Zero Trust Bastion Pvt. Ltd.**
It builds monthly 24×7 rosters across several projects with a real constraint optimiser
(Google OR-Tools CP-SAT). It re-checks every roster with an independent validator, handles
leave, and keeps all data in a SQLite file on your own computer.

> **Status:** built and tested in an isolated Linux cloud workspace. It has **not yet been
> installed or run on Windows**. Local acceptance testing on a ZTB laptop is the next step
> (see [docs/UAT_CHECKLIST.md](docs/UAT_CHECKLIST.md) and [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)).

## What it does

- **Projects, shifts, analysts:** multiple projects, configurable shift templates per project
  (default M 06–15, A 14–23, N 22–07, Asia/Kolkata), minimum and maximum staffing per shift
  and day, skills, and analysts who can work several projects.
- **Automatic generation:** a 10-step wizard drives a CP-SAT model with:
  - hard rules: coverage, approved leave, no overlaps, eligibility and skills, the 5-day /
    2-off week, maximum hours, 11 h rest, consecutive-day and night limits, locks, overnight
    shifts and continuity from the previous month
  - soft goals: fair nights, fair weekends, balanced hours, preferences, fewer shift changes
    and minimum disruption
- **Honest results:** OPTIMAL, FEASIBLE, INFEASIBLE (with the conflicting rules named),
  TIMEOUT or ERROR. Progress shows only what the solver reports. Hard rules are never
  relaxed to force a result.
- **Independent validator:** every generated, imported or hand-edited roster is checked by
  separate code.
- **Leave:** submit, edit, approve or reject, cancel, and partial-day leave. Before you
  decide, see the impact on the roster, replacement suggestions, and a simulated
  regeneration. Regeneration re-solves only the affected days.
- **Roster editor:** monthly matrix, shift-coverage view, week and month calendars, and
  project, analyst and shift filters.
  - Changes: drag-and-drop or cell edits. Every change is validated before it is saved.
  - Also: locks, undo/redo, and draft → published → archived versions.
- **Excel:** 7-sheet editable XLSX export, and XLSX/CSV import with preview, column mapping
  and validation. Includes an adapter for the previous SOC roster layout, and formula-injection
  protection.
- **Local data tools:** backup, restore, delete-everything, and synthetic demo data.

## Quick start (Windows)

**One step:** download [`install.ps1`](https://raw.githubusercontent.com/urschandresh/Skill/ccr-fa255194-qgmtwb/ztb-shift-roster/install.ps1)
and run `powershell -ExecutionPolicy Bypass -File .\install.ps1`. It checks or installs
Python and Node.js (asking first), downloads ShiftOrbit to `Documents\ZTB-ShiftOrbit`, runs
setup and starts the app.

**Or step by step:**

Prerequisites: **Python 3.11+** (python.org, tick "Add to PATH") and **Node.js 20+ LTS**.

```powershell
cd ztb-shift-roster
powershell -ExecutionPolicy Bypass -File .\setup.ps1   # once: venv, packages, build UI
powershell -ExecutionPolicy Bypass -File .\start.ps1   # opens http://127.0.0.1:8000
powershell -ExecutionPolicy Bypass -File .\stop.ps1
```

`start.ps1 -Dev` also runs the Vite dev server on http://127.0.0.1:5173. `start.ps1 -Port 8001`
uses another port. Everything listens on 127.0.0.1 only.

First run: **Settings & data → Backup & data → Load synthetic demo data** to try the tool with
invented analysts, or create your own projects and analysts (or import them from Excel/CSV).

## Quick start (Linux / macOS)

```bash
cd ztb-shift-roster
./setup.sh            # once (add --dev for the test tools)
./start.sh            # http://127.0.0.1:8000   (./start.sh 8001 for another port)
./stop.sh
```

These scripts were run end-to-end from a fresh clone in the build environment (Python 3.11, 3.12
and 3.13 all work).

## Manual start (any OS)

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd ../frontend && npm ci && npm run build
cd ../backend && .venv/bin/python run.py        # http://127.0.0.1:8000
```

## Tests

| Suite | Command | Result in the cloud workspace |
|---|---|---|
| Backend (pytest) | `cd backend && .venv/bin/python -m pytest` | 73 passed |
| Frontend unit (Vitest) | `cd frontend && npm test` | 20 passed |
| Type check | `cd frontend && npm run typecheck` | clean |
| End-to-end (Playwright, desktop + mobile) | `cd frontend && npm run build && npx playwright test` | 8 passed |

`scripts/run-tests.ps1` (Windows) and `scripts/run_tests.sh` run everything.

## Layout

```
backend/app/api         HTTP endpoints (FastAPI)
backend/app/models      SQLAlchemy tables
backend/app/schemas     Pydantic request/response validation
backend/app/services    business logic: generation jobs, leave, Excel, backup
backend/app/solver      CP-SAT model, candidates, preliminary feasibility check
backend/app/validators  independent roster validator
backend/tests           pytest suites (synthetic data only)
frontend/src            React + TypeScript UI (pages, components, services, types, tests)
frontend/e2e            Playwright end-to-end tests
sample-data             SYNTHETIC example files
docs                    architecture, user guide, security, known issues, UAT, phase report
setup.ps1 start.ps1 stop.ps1   Windows scripts
setup.sh start.sh stop.sh      Linux/macOS scripts
```

## Documentation

- [User guide](docs/USER_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md) and [scheduling model](docs/SCHEDULING_MODEL.md)
- [Security assessment](docs/SECURITY.md)
- [Known issues and limitations](docs/KNOWN_ISSUES.md)
- [Local UAT checklist](docs/UAT_CHECKLIST.md)
- [Phase report](docs/PHASE_REPORT.md) · [Implementation plan](docs/IMPLEMENTATION_PLAN.md)

## Data and privacy

All data stays in `data/shiftorbit.db` (plus `data/backups/`). There is no telemetry, no
cloud service, no third-party login and no paid API. The repository contains synthetic data
only; never commit real staff data. See [docs/SECURITY.md](docs/SECURITY.md) for what local
binding does and does not protect against.
