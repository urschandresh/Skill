# Technical architecture

## Overview

```
 Browser (127.0.0.1)                     Python process (127.0.0.1:8000)
┌──────────────────────┐   /api/* JSON   ┌───────────────────────────────────────────────┐
│ React + TypeScript   │ ──────────────▶ │ LocalSecurityMiddleware (Host/Origin/CSRF/size)│
│ Vite build, Tailwind │ X-ZTB-Request:1 │ CORS (local origins only)                      │
│ shadcn/ui, FullCal.  │ ◀────────────── │ FastAPI routers  app/api                       │
│ React Query, RHF+Zod │                 │   │                                            │
└──────────────────────┘                 │   ▼                                            │
        ▲  static files (dist/)          │ services ──▶ problem_builder ──▶ ProblemInstance│
        └─────────────────────────────── │   │            (plain data, no DB)    │        │
                                         │   │                     ┌─────────────┴──────┐ │
                                         │   │  JobManager thread  │ solver (CP-SAT)    │ │
                                         │   │  pool ─────────────▶│ validators (indep.)│ │
                                         │   ▼                     └────────────────────┘ │
                                         │ SQLAlchemy ORM ──▶ SQLite  data/shiftorbit.db   │
                                         └───────────────────────────────────────────────┘
```

One process serves the API and the built frontend, so the browser makes same-origin requests
and nothing else needs configuring. In development, Vite (`127.0.0.1:5173`) proxies `/api` to
the backend.

## Boundaries

| Layer | Package | Depends on | Must not |
|---|---|---|---|
| UI | `frontend/src` | `/api` only | call any other host |
| HTTP | `app/api` | schemas, services | contain business rules beyond request mapping |
| Validation of input | `app/schemas` | – | – |
| Business logic | `app/services` | models, solver, validators | – |
| Problem data | `app/domain.py` | – | import the DB |
| Engine | `app/solver` | `domain` | import models, services or validators |
| Independent checker | `app/validators` | `domain` | import `app.solver` |
| Persistence | `app/models`, `app/db.py` | SQLAlchemy | – |

## Main flows

**Generate.** `POST /api/rosters/generate` validates the request synchronously (bad input
fails fast with 422) and stores a `SolverRun`, then queues it.

The worker thread then:

1. builds a `ProblemInstance`
2. runs the preliminary check; if it finds a definite blocker, the run ends as INFEASIBLE with those reasons
3. solves with CP-SAT
4. re-validates the result with the independent validator
5. saves a new **draft** roster version

The UI polls `GET /api/jobs/{id}`. Cancellation: `POST /api/jobs/{id}/cancel` sets a flag;
a watcher thread calls `CpSolver.stop_search()`.

**Edit.** `POST /api/rosters/{id}/changes` takes slot-based operations (add, remove, move,
lock, unlock). The frontend first sends `dry_run: true`. If the change introduces new hard-rule
violations, the commit is refused (409) unless the user gives an override reason, which is
stored on the assignment and in the audit log. Undo/redo are client-side stacks of inverse
operations, sent through the same validated path.

**Versions.** draft (editable) → published (one per month and project set; previous becomes
archived) → archived. Published or archived rosters are copied to a new draft to change them.
Imported old rosters are **historical** (read-only; used for month continuity).

**Leave.**
- Leave is pending → approved / rejected, or cancelled.
- *Impact* validates the roster with the leave treated as approved, in memory only.
- *Replacements* tries each eligible analyst on each affected shift and ranks those that add no violations.
- *Regenerate* re-solves a date window around the leave with everything else locked. With `simulate`, nothing is saved.

**Excel.**
- Export: a 7-sheet workbook built with openpyxl. Every string goes through `write_cell`, which neutralises formula prefixes.
- Import:
  1. *Preview* parses the file in memory (size, type and zip-bomb limits; macros and formulas rejected) and suggests a column mapping.
  2. *Commit* validates every row and writes all of them or none.

## Database

SQLite with foreign keys, WAL journal and an `app_meta.schema_version`. The tables are created
on first start. A schema-version mismatch refuses to start rather than migrating silently
(see KNOWN_ISSUES). The main tables:

- `projects`, `shift_templates`, `staffing_requirements`, `skills`
- `analysts`, `analyst_projects`
- `scheduling_policies`, `leave_requests`, `availability_exceptions`, `holidays`, `shift_code_mappings`
- `rosters`, `assignments`, `roster_day_markers`
- `solver_runs`, `audit_log`

## Concurrency

The solver runs on a 1-worker thread pool by default, with CP-SAT using up to 8 search
threads. SQLite sessions are per request or per job. Runs left queued or running when the
app stopped are marked failed at the next start.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `ZTB_HOST` | 127.0.0.1 | bind address (non-loopback refused unless `ZTB_ALLOW_NON_LOOPBACK=1`) |
| `ZTB_PORT` | 8000 | port |
| `ZTB_DATA_DIR` | `ztb-shift-roster/data` | database and backups |
| `ZTB_DB_PATH` | `<data>/shiftorbit.db` | database file |
| `ZTB_ALLOWED_ORIGINS` | 127.0.0.1/localhost on the port and 5173 | CORS and Origin allowlist |
| `ZTB_MAX_UPLOAD_MB` | 5 | import file size limit |
| `ZTB_MAX_SOLVER_SECONDS` | 600 | ceiling for time limits |
| `ZTB_ENABLE_API_DOCS` | off | Swagger page (loads assets from a public CDN, so off) |
| `ZTB_LOG_LEVEL` | INFO | logging |
