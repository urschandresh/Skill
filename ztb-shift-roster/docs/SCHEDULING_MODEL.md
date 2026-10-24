# Scheduling model

Source: `backend/app/solver/model.py` (CP-SAT), `backend/app/solver/candidates.py`,
`backend/app/validators/roster_validator.py` (independent check), rule semantics in
`backend/app/domain.py`.

## Decision variables

One boolean `x[a, p, s, d]` per **candidate slot**: analyst `a`, project `p`, shift template
`s`, date `d` (the date the shift starts). A slot is a candidate only if all of these hold:

- the shift template is active and its project is in the run
- the analyst is eligible for the project; if the eligibility lists shifts, the code is allowed
- the analyst has every skill the project and the shift require
- no approved leave, availability exception or work-blocking holiday covers it

Slots excluded for leave or absence are kept for diagnostics: a locked slot that is blocked
is reported, not dropped.

## Time handling

Every shift is converted to an absolute interval using its project's IANA timezone (default
Asia/Kolkata), so overnight shifts (`end <= start`) and any DST zone are handled exactly. The
validator does the same with timezone-aware `datetime` objects instead of epoch minutes.

## Hard constraints

| # | Rule | Formulation |
|---|---|---|
| 1 | Minimum (and optional maximum) staffing per project/shift/day | `Σ x ≥ min − fixed`, `Σ x ≤ max − fixed` |
| 2 | Approved leave | no variable exists for blocked slots |
| 3 | No overlaps (also across projects) and minimum rest (default 11 h) | for every pair of the analyst's slots whose intervals overlap or leave a gap shorter than the rest time: `x_i + x_j ≤ 1`; against fixed shifts: `x = 0` |
| 4 | Eligibility and skills | candidate filtering |
| 5 | Weekly working days (default exactly 5, i.e. 2 offs) | per analyst-week: `lower ≤ worked ≤ upper` (see below) |
| 6 | Maximum weekly hours | `Σ minutes·x + fixed ≤ max_hours·60` |
| 7 | One shift per calendar day (default on) | `Σ_d x ≤ 1` |
| 8 | Maximum consecutive working days | every window of `limit+1` known days: `Σ worked ≤ limit` |
| 9 | Maximum consecutive nights | same, over night shifts |
| 10 | Locked assignments | `x = 1` |
| 11 | Previous-month continuity | the previous month's published (else imported historical) roster provides fixed shifts for rest, consecutive and weekly rules |
| 12 | Other published rosters in the same month (other projects) | fixed shifts, so a separately rostered project cannot double-book an analyst |

**Weekly bounds** for an analyst and a week. N = working days per week, L = full-day leave
days, B = fully unavailable days, U = days whose roster is unknown:

- `upper = N − L` if leave counts as a working day (default), else `min(N, 7 − L)`
- `lower = max(0, min(upper, 7 − B) − U)` in *exact* mode, `0` in *max* mode
- In a week that straddles the roster start, days already worked in the previous roster count,
  but the bounds are limited to what this roster can still change. This is reported as an
  explicit `weekly_days_inherited` warning, never silently.

## Objective (minimised)

All terms are integers in "shift-equivalent" units, each multiplied by the policy weight.

| Term | Meaning |
|---|---|
| `fair_nights` | max − min of night shifts per analyst, normalised by days available (leave reduces the expected share) |
| `fair_weekends` | same for Saturday/Sunday shifts |
| `balanced_hours` | same for worked minutes |
| `preferences` | +2 for an avoided shift, +1 for a non-preferred shift, +1 for working a preferred day off |
| `shift_changes` | +1 each time consecutive worked days use different shift codes |
| `disruption` | when regenerating: +1 per baseline assignment removed and per new assignment (baseline used as a solver hint) |

## Status codes

| Status | Meaning |
|---|---|
| OPTIMAL | proven best for the objective |
| FEASIBLE | valid roster; time limit reached (or stopped by user) before proving optimality |
| INFEASIBLE | proven impossible. A second solve with assumption literals names a set of conflicting rule groups (coverage cells, weekly rules, locks…). If the preliminary check already found a definite blocker, the solver is not run. |
| TIMEOUT | no roster found and infeasibility not proven within the time limit |
| CANCELLED | stopped by the user before any roster was found (job state) |
| ERROR | model invalid, internal error, or the independent validator rejected the solver output (that roster is never saved) |

## Preliminary feasibility check

These are necessary conditions only (`solver/feasibility.py`):

- every required shift has enough candidates
- a per-day bipartite matching of required positions to analysts
- weekly analyst-day capacity against demand
- locked shifts are usable and do not clash
- every analyst can work something

## Determinism

The solver uses a fixed random seed but several worker threads, so two runs can return
different rosters of equal quality. Saved rosters are versioned, so results are reproducible
from the database.
