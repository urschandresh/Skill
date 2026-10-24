"""OR-Tools CP-SAT roster model.

Decision variables: one boolean ``x[analyst, project, shift, date]`` per usable slot (see
``candidates.py``). Hard rules are constraints; preferences and fairness are the objective.
Hard rules are never relaxed: if they cannot all hold, the result is INFEASIBLE and a second,
assumption-based solve names the rule groups that conflict.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from ortools.sat.python import cp_model

from ..domain import ProblemInstance, Slot
from .candidates import Candidates, build_candidates, shift_interval, week_start

# One "shift-equivalent" in objective units: 100 (fairness normalisation) x 540 minutes.
UNIT = 100 * 540
WEEKEND = (5, 6)


@dataclass
class SolveResult:
    status: str  # OPTIMAL | FEASIBLE | INFEASIBLE | TIMEOUT | CANCELLED | ERROR
    assignments: list[Slot] = field(default_factory=list)
    objective: float | None = None
    best_bound: float | None = None
    wall_time: float = 0.0
    solutions_found: int = 0
    stopped_by_user: bool = False
    message: str = ""
    diagnostics: list[dict[str, Any]] = field(default_factory=list)
    objective_breakdown: dict[str, int] = field(default_factory=dict)
    model_stats: dict[str, int] = field(default_factory=dict)

    @property
    def has_solution(self) -> bool:
        return self.status in ("OPTIMAL", "FEASIBLE")


class _ProgressCallback(cp_model.CpSolverSolutionCallback):
    def __init__(self, handle) -> None:
        super().__init__()
        self.handle = handle
        self.count = 0

    def on_solution_callback(self) -> None:
        self.count += 1
        if self.handle is not None:
            self.handle.report(
                phase="solving",
                solutions_found=self.count,
                objective=self.objective_value,
                best_bound=self.best_objective_bound,
                solver_wall_time=round(self.wall_time, 2),
            )
            if self.handle.cancelled:
                self.stop_search()


class RosterModel:
    def __init__(self, inst: ProblemInstance, with_assumptions: bool = False, with_objective: bool = True):
        self.inst = inst
        self.policy = inst.policy
        self.m = cp_model.CpModel()
        self.with_assumptions = with_assumptions
        self.cands: Candidates = build_candidates(inst)
        self.x: dict[Slot, cp_model.IntVar] = {}
        self.groups: dict[str, tuple[cp_model.IntVar, dict[str, Any]]] = {}
        self.terms: dict[str, cp_model.LinearExprT] = {}
        self.dates = inst.dates()
        self.horizon = set(self.dates)

        for slot in self.cands.slots:
            self.x[slot] = self.m.new_bool_var(f"x_{slot.analyst_id}_{slot.shift_id}_{slot.date:%Y%m%d}")

        self._index()
        self._coverage()
        self._one_per_day()
        self._rest_and_overlap()
        self._weekly()
        self._consecutive()
        self._locks()
        if with_objective:
            self._objective()
        if with_assumptions:
            self.m.add_assumptions([lit for lit, _ in self.groups.values()])

    # ------------------------------------------------------------------ helpers

    def _guard(self, key: str, info: dict[str, Any]) -> cp_model.IntVar | None:
        if not self.with_assumptions:
            return None
        lit = self.m.new_bool_var(f"g_{key}")
        self.groups[key] = (lit, info)
        return lit

    def _bound(self, terms: list, const: int, lo: int | None, hi: int | None, guard) -> None:
        """Add lo <= sum(terms) + const <= hi, optionally enforced only when guard is true."""
        if not terms:
            ok = (lo is None or const >= lo) and (hi is None or const <= hi)
            if not ok:
                self.m.add_bool_or([guard.Not()] if guard is not None else [])
            return
        expr = sum(terms) + const
        cts = []
        if lo is not None:
            cts.append(self.m.add(expr >= lo))
        if hi is not None:
            cts.append(self.m.add(expr <= hi))
        if guard is not None:
            for ct in cts:
                ct.only_enforce_if(guard)

    def _index(self) -> None:
        inst = self.inst
        self.by_ad: dict[tuple[int, date], list[Slot]] = defaultdict(list)
        self.by_psd: dict[tuple[int, int, date], list[Slot]] = defaultdict(list)
        self.by_a: dict[int, list[Slot]] = defaultdict(list)
        for slot in self.x:
            self.by_ad[(slot.analyst_id, slot.date)].append(slot)
            self.by_psd[(slot.project_id, slot.shift_id, slot.date)].append(slot)
            self.by_a[slot.analyst_id].append(slot)
        self.fixed_by_a: dict[int, list[Slot]] = defaultdict(list)
        self.fixed_days: dict[int, set[date]] = defaultdict(set)
        self.fixed_nights: dict[int, set[date]] = defaultdict(set)
        self.fixed_psd: dict[tuple[int, int, date], int] = defaultdict(int)
        self.fixed_code_by_day: dict[tuple[int, date], str] = {}
        for f in inst.fixed:
            if f.analyst_id not in inst.analysts or f.shift_id not in inst.shifts:
                continue
            self.fixed_by_a[f.analyst_id].append(f)
            self.fixed_days[f.analyst_id].add(f.date)
            sh = inst.shifts[f.shift_id]
            if sh.is_night:
                self.fixed_nights[f.analyst_id].add(f.date)
            self.fixed_psd[(f.project_id, f.shift_id, f.date)] += 1
            self.fixed_code_by_day[(f.analyst_id, f.date)] = sh.code
        self.minutes: dict[Slot, int] = {}
        for slot in list(self.x) + list(inst.fixed):
            if slot.shift_id in inst.shifts:
                s, e = shift_interval(inst.shifts[slot.shift_id], slot.date)
                self.minutes[slot] = e - s

        # Worked-day and night expressions for horizon days.
        self.worked: dict[tuple[int, date], Any] = {}
        self.night: dict[tuple[int, date], Any] = {}
        for a in inst.analysts:
            for d in self.dates:
                slots = self.by_ad.get((a, d), [])
                nights = [s for s in slots if inst.shifts[s.shift_id].is_night]
                self.worked[(a, d)] = self._or_expr(slots, f"w_{a}_{d:%Y%m%d}")
                self.night[(a, d)] = self._or_expr(nights, f"n_{a}_{d:%Y%m%d}")

    def _or_expr(self, slots: list[Slot], name: str):
        if not slots:
            return 0
        if self.policy.one_shift_per_day or len(slots) == 1:
            # At most one shift per day is enforced, so the sum is already 0/1.
            return sum(self.x[s] for s in slots)
        v = self.m.new_bool_var(name)
        self.m.add_max_equality(v, [self.x[s] for s in slots])
        return v

    def day_status(self, analyst_id: int, d: date):
        """(worked, night) for any date: expressions in the horizon, ints when known, None if unknown."""
        fixed_w = 1 if d in self.fixed_days.get(analyst_id, ()) else 0
        fixed_n = 1 if d in self.fixed_nights.get(analyst_id, ()) else 0
        if d in self.horizon:
            if fixed_w:
                return 1, fixed_n
            return self.worked[(analyst_id, d)], self.night[(analyst_id, d)]
        known_from = self.inst.history_known_from.get(analyst_id)
        if d < self.inst.start_date and known_from is not None and d >= known_from:
            return fixed_w, fixed_n
        return None, None

    # ------------------------------------------------------------------ hard constraints

    def _coverage(self) -> None:
        for (p, s, d), (mn, mx) in self.inst.requirements.items():
            terms = [self.x[slot] for slot in self.by_psd.get((p, s, d), [])]
            const = self.fixed_psd.get((p, s, d), 0)
            if mn > 0:
                guard = self._guard(f"cov_{p}_{s}_{d:%Y%m%d}", {"type": "coverage", "project_id": p,
                                                                   "shift_id": s, "date": d.isoformat(), "min": mn})
                self._bound(terms, const, mn, None, guard)
            if mx is not None:
                guard = self._guard(f"covmax_{p}_{s}_{d:%Y%m%d}", {"type": "coverage_max", "project_id": p,
                                                                      "shift_id": s, "date": d.isoformat(), "max": mx})
                self._bound(terms, const, None, mx, guard)

    def _one_per_day(self) -> None:
        if not self.policy.one_shift_per_day:
            return
        for (a, d), slots in self.by_ad.items():
            busy = 1 if d in self.fixed_days.get(a, ()) else 0
            self._bound([self.x[s] for s in slots], busy, None, 1, None)

    def _rest_and_overlap(self) -> None:
        rest = self.policy.min_rest_hours * 60
        for a in self.inst.analysts:
            items = []
            for slot in self.by_a.get(a, []):
                s, e = shift_interval(self.inst.shifts[slot.shift_id], slot.date)
                items.append((s, e, slot, False))
            for slot in self.fixed_by_a.get(a, []):
                s, e = shift_interval(self.inst.shifts[slot.shift_id], slot.date)
                items.append((s, e, slot, True))
            items.sort(key=lambda t: t[0])
            for i, (si, ei, slot_i, fixed_i) in enumerate(items):
                for sj, ej, slot_j, fixed_j in items[i + 1 :]:
                    if sj >= ei + rest:
                        break
                    if fixed_i and fixed_j:
                        continue  # both outside our control; the validator reports it
                    if fixed_i:
                        self.m.add(self.x[slot_j] == 0)
                    elif fixed_j:
                        self.m.add(self.x[slot_i] == 0)
                    else:
                        self.m.add(self.x[slot_i] + self.x[slot_j] <= 1)

    def _weeks(self) -> list[date]:
        first = week_start(self.inst.start_date, self.policy.week_start_day)
        weeks = []
        while first <= self.inst.end_date:
            weeks.append(first)
            first += timedelta(days=7)
        return weeks

    def weekly_bounds(self, analyst_id: int, ws: date) -> tuple[int, int, list[date]]:
        """(lower, upper, unknown_days) for one analyst and week. Mirrors domain.py docs."""
        pol = self.policy
        absn = self.cands.absences
        days = [ws + timedelta(days=i) for i in range(7)]
        leave = sum(1 for d in days if absn.full_leave_days(analyst_id, d))
        unavailable = sum(1 for d in days if absn.fully_unavailable(analyst_id, d))
        unknown = [d for d in days if self.day_status(analyst_id, d)[0] is None]
        unknown_free = sum(1 for d in unknown if not absn.fully_unavailable(analyst_id, d))
        n = pol.working_days_per_week
        upper = max(0, n - leave) if pol.leave_counts_as_working_day else min(n, 7 - leave)
        if pol.weekly_mode == "exact":
            lower = max(0, min(upper, 7 - unavailable) - unknown_free)
        else:
            lower = 0
        # Days before the roster start are fixed; bound the rule by what is still changeable.
        history = sum(1 for d in days if d < self.inst.start_date and self.day_status(analyst_id, d)[0] == 1)
        if history:
            open_days = sum(1 for d in days if d in self.horizon and not absn.fully_unavailable(analyst_id, d)
                            and d not in self.fixed_days.get(analyst_id, ()))
            fixed_in_h = sum(1 for d in days if d in self.horizon and d in self.fixed_days.get(analyst_id, ()))
            lower = min(lower, history + fixed_in_h + open_days)
            upper = max(upper, history)
        return lower, upper, unknown

    def _weekly(self) -> None:
        pol = self.policy
        for a, analyst in self.inst.analysts.items():
            max_minutes = (analyst.max_hours_per_week or pol.max_hours_per_week) * 60
            for ws in self._weeks():
                days = [ws + timedelta(days=i) for i in range(7)]
                lower, upper, _unknown = self.weekly_bounds(a, ws)
                terms, const = [], 0
                for d in days:
                    w, _n = self.day_status(a, d)
                    if w is None:
                        continue
                    if isinstance(w, int):
                        const += w
                    else:
                        terms.append(w)
                guard = self._guard(f"week_{a}_{ws:%Y%m%d}", {"type": "weekly_days", "analyst_id": a,
                                                              "week_start": ws.isoformat(), "lower": lower,
                                                              "upper": upper})
                self._bound(terms, const, lower if lower > 0 else None, upper, guard)

                hterms, hconst = [], 0
                for d in days:
                    for slot in self.by_ad.get((a, d), []):
                        hterms.append(self.minutes[slot] * self.x[slot])
                for f in self.fixed_by_a.get(a, []):
                    if ws <= f.date < ws + timedelta(days=7):
                        hconst += self.minutes.get(f, 0)
                if hterms:
                    guard = self._guard(f"hours_{a}_{ws:%Y%m%d}", {"type": "weekly_hours", "analyst_id": a,
                                                                   "week_start": ws.isoformat(),
                                                                   "max_hours": max_minutes // 60})
                    self._bound(hterms, hconst, None, max_minutes, guard)

    def _windows(self, a: int, limit: int, kind: str) -> None:
        span = limit + 1
        first = self.inst.start_date - timedelta(days=limit)
        all_days = [first + timedelta(days=i) for i in range((self.inst.end_date - first).days + 1)]
        idx = 0 if kind == "days" else 1
        values = [self.day_status(a, d)[idx] for d in all_days]
        guard = None
        for i in range(len(all_days) - span + 1):
            window = values[i : i + span]
            if any(v is None for v in window):
                continue
            terms = [v for v in window if not isinstance(v, int)]
            if not terms:
                continue
            const = sum(v for v in window if isinstance(v, int))
            if guard is None:
                guard = self._guard(f"{kind}_{a}", {"type": "consecutive_" + kind, "analyst_id": a, "limit": limit})
            self._bound(terms, const, None, limit, guard)

    def _consecutive(self) -> None:
        for a in self.inst.analysts:
            self._windows(a, self.policy.max_consecutive_work_days, "days")
            self._windows(a, self.policy.max_consecutive_nights, "nights")

    def _locks(self) -> None:
        for slot in self.inst.locked:
            guard = self._guard(
                f"lock_{slot.analyst_id}_{slot.project_id}_{slot.shift_id}_{slot.date:%Y%m%d}",
                {"type": "locked", "analyst_id": slot.analyst_id, "project_id": slot.project_id,
                 "shift_id": slot.shift_id, "date": slot.date.isoformat()},
            )
            if slot in self.x:
                ct = self.m.add(self.x[slot] == 1)
                if guard is not None:
                    ct.only_enforce_if(guard)
            else:
                self.m.add_bool_or([guard.Not()] if guard is not None else [])

    # ------------------------------------------------------------------ objective

    def _availability(self) -> dict[int, int]:
        absn = self.cands.absences
        return {
            a: sum(1 for d in self.dates if not absn.fully_unavailable(a, d))
            for a in self.inst.analysts
        }

    def _spread(self, name: str, values: dict[int, Any], avail: dict[int, int], scale: int, max_value: int):
        """max - min of availability-normalised values; None when fewer than two analysts."""
        group = [a for a in values if avail.get(a, 0) > 0]
        if len(group) < 2:
            return None
        horizon = len(self.dates)
        norms, top = [], 0
        for a in group:
            coef = round(100 * horizon / avail[a]) * scale
            ub = coef * max_value
            top = max(top, ub)
            v = self.m.new_int_var(0, ub, f"{name}_norm_{a}")
            self.m.add(v == coef * values[a])
            norms.append(v)
        hi = self.m.new_int_var(0, top, f"{name}_max")
        lo = self.m.new_int_var(0, top, f"{name}_min")
        self.m.add_max_equality(hi, norms)
        self.m.add_min_equality(lo, norms)
        return hi - lo

    def _objective(self) -> None:
        inst, w = self.inst, self.policy.weights
        avail = self._availability()
        shifts = inst.shifts

        nights = {a: sum(self.x[s] for s in self.by_a[a] if shifts[s.shift_id].is_night)
                  for a in inst.analysts if any(shifts[s.shift_id].is_night for s in self.by_a.get(a, []))}
        weekends = {a: sum(self.x[s] for s in self.by_a[a] if s.date.weekday() in WEEKEND)
                    for a in inst.analysts if any(s.date.weekday() in WEEKEND for s in self.by_a.get(a, []))}
        minutes = {a: sum(self.minutes[s] * self.x[s] for s in self.by_a[a])
                   for a in inst.analysts if self.by_a.get(a)}

        terms: dict[str, Any] = {}
        if w.get("fair_nights", 0):
            t = self._spread("nights", nights, avail, 540, len(self.dates))
            if t is not None:
                terms["fair_nights"] = t
        if w.get("fair_weekends", 0):
            t = self._spread("weekends", weekends, avail, 540, len(self.dates))
            if t is not None:
                terms["fair_weekends"] = t
        if w.get("balanced_hours", 0):
            t = self._spread("hours", minutes, avail, 1, len(self.dates) * 1440)
            if t is not None:
                terms["balanced_hours"] = t

        if w.get("preferences", 0):
            pref_terms = []
            for a, analyst in inst.analysts.items():
                for slot in self.by_a.get(a, []):
                    code = shifts[slot.shift_id].code
                    penalty = 0
                    if code in analyst.avoid_shifts:
                        penalty += 2
                    if analyst.preferred_shifts and code not in analyst.preferred_shifts:
                        penalty += 1
                    if slot.date.weekday() in analyst.preferred_off_days:
                        penalty += 1
                    if penalty:
                        pref_terms.append(penalty * self.x[slot])
            if pref_terms:
                terms["preferences"] = UNIT * sum(pref_terms)

        if w.get("shift_changes", 0) and self.policy.one_shift_per_day:
            change_vars = []
            codes = sorted({sh.code for sh in shifts.values()})
            for a in inst.analysts:
                days = [self.inst.start_date - timedelta(days=1), *self.dates]
                for d0, d1 in zip(days, days[1:]):
                    w1, _ = self.day_status(a, d1)
                    if w1 is None or isinstance(w1, int) and w1 == 0:
                        continue
                    c = None
                    for code in codes:
                        y0 = self._code_expr(a, d0, code)
                        y1 = self._code_expr(a, d1, code)
                        if isinstance(y0, int) and y0 == 0:
                            continue
                        if c is None:
                            c = self.m.new_bool_var(f"chg_{a}_{d1:%Y%m%d}")
                            change_vars.append(c)
                        self.m.add(c >= y0 + w1 - y1 - 1)
            if change_vars:
                terms["shift_changes"] = UNIT * sum(change_vars)

        if w.get("disruption", 0) and inst.baseline:
            base = set(inst.baseline)
            removed = [1 - self.x[s] for s in base if s in self.x]
            lost = sum(1 for s in base if s not in self.x)  # constant: no longer possible at all
            added = [self.x[s] for s in self.x if s not in base]
            terms["disruption"] = UNIT * (sum(removed) + sum(added) + lost)
            for s, var in self.x.items():
                self.m.add_hint(var, 1 if s in base else 0)

        self.terms = terms
        if terms:
            self.m.minimize(sum(int(w.get(k, 0)) * t for k, t in terms.items()))

    def _code_expr(self, a: int, d: date, code: str):
        if d in self.horizon:
            if self.fixed_code_by_day.get((a, d)) == code:
                return 1
            slots = [s for s in self.by_ad.get((a, d), []) if self.inst.shifts[s.shift_id].code == code]
            return sum(self.x[s] for s in slots) if slots else 0
        return 1 if self.fixed_code_by_day.get((a, d)) == code else 0


def _solver(time_limit: float, workers: int | None = None) -> cp_model.CpSolver:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    solver.parameters.num_workers = workers or max(1, min(8, os.cpu_count() or 1))
    solver.parameters.random_seed = 42
    return solver


def _run_with_cancel(solver, model, callback, handle, time_limit, stats):
    """Solve while a watcher thread forwards cancellation to CP-SAT.

    ``stop_search`` only affects a search that is already running, so the watcher keeps
    re-issuing it until the solve returns.
    """
    if handle is None:
        return solver.solve(model, callback)
    handle.report(phase="solving", time_limit_seconds=time_limit, **stats)
    done = threading.Event()

    def watch() -> None:
        while not done.wait(0.2):
            if handle.cancelled:
                solver.stop_search()

    watcher = threading.Thread(target=watch, name="cpsat-cancel-watch", daemon=True)
    watcher.start()
    try:
        return solver.solve(model, callback)
    finally:
        done.set()
        watcher.join()


def solve(inst: ProblemInstance, time_limit: float | None = None, handle=None) -> SolveResult:
    """Build and solve the model. ``handle`` (a JobHandle) receives progress and cancellation."""
    time_limit = time_limit or inst.policy.solver_time_limit_seconds
    t0 = time.monotonic()
    if handle is not None:
        handle.report(phase="building_model")
    try:
        rm = RosterModel(inst)
    except Exception as exc:  # pragma: no cover - defensive
        return SolveResult(status="ERROR", message=f"Model construction failed: {type(exc).__name__}")
    stats = {
        "decision_variables": len(rm.x),
        "analysts": len(inst.analysts),
        "days": len(rm.dates),
        "requirements": len(inst.requirements),
        "locked": len(inst.locked),
        "fixed_outside_roster": len(inst.fixed),
    }
    if handle is not None and handle.cancelled:
        return SolveResult(status="CANCELLED", stopped_by_user=True, model_stats=stats,
                           wall_time=round(time.monotonic() - t0, 3), message="Cancelled before solving started.")
    solver = _solver(time_limit)
    cb = _ProgressCallback(handle)
    status = _run_with_cancel(solver, rm.m, cb, handle, time_limit, stats)
    stopped = handle is not None and handle.cancelled
    name = solver.status_name(status)
    result = SolveResult(status="ERROR", wall_time=round(time.monotonic() - t0, 3),
                         solutions_found=cb.count, stopped_by_user=stopped, model_stats=stats)

    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        result.status = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
        result.assignments = sorted(s for s, v in rm.x.items() if solver.value(v))
        if rm.terms:
            result.objective = solver.objective_value
            result.best_bound = solver.best_objective_bound
            result.objective_breakdown = {k: int(solver.value(t)) for k, t in rm.terms.items()}
        if stopped:
            result.message = "Stopped by user; returning the best roster found so far."
        elif result.status == "FEASIBLE":
            result.message = f"Time limit of {time_limit}s reached; the roster is valid but may not be optimal."
        else:
            result.message = "Optimal roster found."
    elif status == cp_model.INFEASIBLE:
        result.status = "INFEASIBLE"
        result.message = "No roster satisfies every hard constraint."
        remaining = max(5.0, min(20.0, time_limit))
        result.diagnostics = diagnose(inst, remaining, handle)
    elif status == cp_model.UNKNOWN:
        if stopped:
            result.status = "CANCELLED"
            result.message = "Stopped by user before any roster was found."
        else:
            result.status = "TIMEOUT"
            result.message = (f"No roster found within {time_limit}s and infeasibility was not proven. "
                              "Increase the time limit or simplify the request.")
    else:
        result.status = "ERROR"
        result.message = f"Solver returned {name}."
    return result


def diagnose(inst: ProblemInstance, time_limit: float, handle=None) -> list[dict[str, Any]]:
    """Name a set of hard-rule groups that cannot hold together (an infeasibility core)."""
    if handle is not None:
        handle.report(phase="diagnosing")
    rm = RosterModel(inst, with_assumptions=True, with_objective=False)
    solver = _solver(time_limit)
    status = _run_with_cancel(solver, rm.m, None, handle, time_limit, {"phase_detail": "diagnosis"})
    if status != cp_model.INFEASIBLE:
        return [{"type": "diagnosis_incomplete",
                 "message": "Could not isolate the conflicting rules within the diagnosis time limit."}]
    by_index = {lit.index: info for lit, info in rm.groups.values()}
    core = [by_index[i] for i in solver.sufficient_assumptions_for_infeasibility() if i in by_index]
    if not core:
        return [{"type": "structural",
                 "message": "Conflict among always-on rules (eligibility, leave, rest/overlap, one shift per day)."}]
    return [{**info, "message": describe(inst, info)} for info in core]


def describe(inst: ProblemInstance, info: dict[str, Any]) -> str:
    """Plain-language sentence for one rule group of an infeasibility core."""
    def acode(a):
        return inst.analysts[a].code if a in inst.analysts else f"#{a}"

    def slot(p, s):
        pc = inst.projects[p].code if p in inst.projects else p
        sc = inst.shifts[s].code if s in inst.shifts else s
        return f"{pc}/{sc}"

    pol = inst.policy
    t = info.get("type")
    if t == "coverage":
        return f"{slot(info['project_id'], info['shift_id'])} on {info['date']} needs at least {info['min']} analyst(s)"
    if t == "coverage_max":
        return f"{slot(info['project_id'], info['shift_id'])} on {info['date']} allows at most {info['max']} analyst(s)"
    if t == "weekly_days":
        a = info["analyst_id"]
        days = info["lower"] if info["lower"] == info["upper"] else f"{info['lower']}-{info['upper']}"
        return f"{acode(a)} must work {days} day(s) in the week of {info['week_start']}"
    if t == "weekly_hours":
        return f"{acode(info['analyst_id'])} may work at most {info['max_hours']} h in the week of {info['week_start']}"
    if t == "consecutive_days":
        return f"{acode(info['analyst_id'])} may work at most {info['limit']} consecutive days"
    if t == "consecutive_nights":
        return f"{acode(info['analyst_id'])} may work at most {info['limit']} consecutive nights"
    if t == "locked":
        return f"Locked shift {slot(info['project_id'], info['shift_id'])} for {acode(info['analyst_id'])} on {info['date']} must be kept"
    return f"{t} (min rest {pol.min_rest_hours} h)"
