# ZTB ShiftOrbit: working notes for Claude

Local-first SOC shift roster maker (FastAPI + OR-Tools CP-SAT + SQLite backend, React/Vite
frontend). See README.md for features and docs/ARCHITECTURE.md for design.

## Rules that must not be broken

- Never relax a hard constraint to make the solver succeed; report INFEASIBLE with diagnostics.
- Never fabricate solver progress or status. Progress comes only from CP-SAT callbacks.
- The validator (`backend/app/validators`) must stay independent: it must not import `app.solver`.
  Any rule change goes into `app/domain.py` docs, the solver AND the validator, with tests.
- Local-only: the backend refuses non-loopback hosts. Every state-changing API call needs the
  `X-ZTB-Request: 1` header (frontend `services/api.ts` adds it). Do not weaken this.
- Synthetic data only in the repo, tests and fixtures (codes `SYN-…`). Never add real staff data.
- Spreadsheet output must go through `excel_common.write_cell` (formula-injection guard).

## Commands

```bash
cd backend && .venv/bin/python -m pytest             # backend tests (~1 min)
cd frontend && npm run typecheck && npm test           # TS + Vitest
cd frontend && npm run build && PW_CHROMIUM=/opt/pw-browsers/chromium npx playwright test   # E2E
cd backend && .venv/bin/python run.py                  # app on http://127.0.0.1:8000 (serves frontend/dist)
python scripts/make_synthetic_fixtures.py              # regenerate sample-data/
```

The venv is Python 3.11 (`backend/.venv`); keep code 3.11-compatible.

## Where things live

- Problem data model and rule semantics: `backend/app/domain.py`
- DB → problem: `backend/app/services/problem_builder.py`
- CP-SAT model: `backend/app/solver/model.py`; pre-solve checks: `solver/feasibility.py`
- Jobs, versions, validated edits, publish: `backend/app/services/roster_service.py`
- Excel: `services/excel_export.py`, `services/excel_import.py`
- UI roster editor: `frontend/src/pages/RosterPage.tsx`, `frontend/src/components/roster/`
