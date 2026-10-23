# ZTB ShiftOrbit: implementation plan

ShiftOrbit is a local-first SOC shift roster maker for Zero Trust Bastion Pvt. Ltd.

## Execution environment note

Development and automated testing for this build happened in an isolated Linux cloud
container (Python 3.11.17, Node 22, Chromium for Playwright). **Nothing here has been
installed or run on a Windows machine yet.** The PowerShell scripts (`setup.ps1`,
`start.ps1`, `stop.ps1`) were written for Windows but could not be executed in the
container (no PowerShell available). Local UAT on Windows is Phase 8 and is the
user's step; see `docs/UAT_CHECKLIST.md`.

## Architecture decisions

| Concern | Decision | Why |
|---|---|---|
| Process model | One FastAPI process on `127.0.0.1:8000` serves both the API and the built React app | One port, same-origin requests, nothing else to configure. Vite dev server (`127.0.0.1:5173`) is optional for development. |
| Storage | SQLite file in `ztb-shift-roster/data/` via SQLAlchemy 2 ORM | Local, parameterized queries, easy backup with SQLite's online backup API. |
| Schema management | `create_all` plus a stored schema version | Single-user local app; no Alembic dependency. A version mismatch refuses to start instead of silently migrating. |
| Solver | OR-Tools CP-SAT, binary `x[analyst, project, shift, date]` | Required; exact constraint model with real status codes. |
| Solver isolation | `app/solver` takes a plain-data `ProblemInstance`, knows nothing about the DB | Testable without a DB; the validator gets the same plain data. |
| Validator | `app/validators` re-implements every hard rule with its own interval maths, never imports the solver | An independent check catches solver-model bugs instead of repeating them. |
| Async solving | In-process thread pool + job table; UI polls `/api/jobs/{id}` | No broker needed locally. Cancellation uses CP-SAT `stop_search`. |
| Progress | Only real data: elapsed time vs. limit, solutions found, objective, best bound | The brief forbids fabricated percentages. |
| Browser-origin protection | Host allowlist, CORS allowlist, Origin check, and a required custom header on every state-changing request | Localhost alone is not an authentication boundary. |

## Phases

1. **Foundations**: settings, DB, ORM models, security middleware, health endpoint, test harness.
2. **Management**: CRUD for projects, shift templates, skills, staffing, policies, analysts, eligibility, availability, holidays, shift-code mappings.
3. **Engine**: problem builder, CP-SAT model, independent validator, preliminary feasibility check, infeasibility diagnostics, async jobs.
4. **Leave and regeneration**: leave lifecycle, impact assessment, replacement suggestions, pending-leave simulation, minimum-disruption regeneration.
5. **Calendar and dashboard**: React app, roster matrix, FullCalendar views, drag-and-drop with validation, undo/redo, draft and published versions, dashboard.
6. **Excel**: XLSX export (7 sheets), XLSX/CSV import with preview, mapping and validation, historical SOC roster adapter, round-trip tests.
7. **Hardening and tests**: security tests, input fuzz cases, Playwright end-to-end, Windows scripts, docs.
8. **Local UAT**: performed by ZTB on Windows using `docs/UAT_CHECKLIST.md`.

Results and remaining gaps for each phase are recorded in `docs/PHASE_REPORT.md`.
