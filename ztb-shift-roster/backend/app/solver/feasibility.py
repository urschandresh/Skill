"""Preliminary feasibility check run before the solver.

These are necessary conditions only. Passing them does not guarantee that a roster
exists (the solver decides that), but each failure is a definite reason why none can.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from ..domain import ProblemInstance, Slot
from .candidates import build_candidates, shift_interval, week_start


def _max_matching(slots: list[Any], edges: dict[Any, list[int]]) -> int:
    match: dict[int, int] = {}

    def try_assign(i: int, seen: set[int]) -> bool:
        for a in edges.get(slots[i], []):
            if a in seen:
                continue
            seen.add(a)
            if a not in match or try_assign(match[a], seen):
                match[a] = i
                return True
        return False

    return sum(1 for i in range(len(slots)) if try_assign(i, set()))


def preliminary_check(inst: ProblemInstance) -> dict[str, Any]:
    cands = build_candidates(inst)
    pol = inst.policy
    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    def pcode(p: int) -> str:
        return inst.projects[p].code if p in inst.projects else str(p)

    def scode(s: int) -> str:
        return inst.shifts[s].code if s in inst.shifts else str(s)

    def acode(a: int) -> str:
        return inst.analysts[a].code if a in inst.analysts else str(a)

    by_psd: dict[tuple[int, int, date], list[int]] = defaultdict(list)
    for slot in cands.slots:
        by_psd[(slot.project_id, slot.shift_id, slot.date)].append(slot.analyst_id)
    blocked_by_psd: dict[tuple[int, int, date], int] = defaultdict(int)
    for slot in cands.blocked:
        blocked_by_psd[(slot.project_id, slot.shift_id, slot.date)] += 1
    fixed_psd: dict[tuple[int, int, date], int] = defaultdict(int)
    fixed_days: dict[int, set[date]] = defaultdict(set)
    for f in inst.fixed:
        fixed_psd[(f.project_id, f.shift_id, f.date)] += 1
        fixed_days[f.analyst_id].add(f.date)

    need: dict[tuple[int, int, date], int] = {}
    total_demand = 0
    for key, (mn, _mx) in inst.requirements.items():
        n = max(0, mn - fixed_psd.get(key, 0))
        if n:
            need[key] = n
            total_demand += n
        available = len(by_psd.get(key, []))
        if n > available:
            p, s, d = key
            issues.append({
                "type": "shift_shortage", "project_id": p, "shift_id": s, "date": d.isoformat(),
                "required": n, "available": available, "on_leave_or_blocked": blocked_by_psd.get(key, 0),
                "message": f"{pcode(p)}/{scode(s)} on {d}: needs {n}, only {available} eligible analyst(s) available"
                           + (f" ({blocked_by_psd[key]} on leave/blocked)" if blocked_by_psd.get(key) else ""),
            })

    if pol.one_shift_per_day:
        for d in inst.dates():
            slots: list[tuple[int, int, int]] = []
            edges: dict[tuple[int, int, int], list[int]] = {}
            for (p, s, dd), n in need.items():
                if dd != d:
                    continue
                for k in range(n):
                    key = (p, s, k)
                    slots.append(key)
                    edges[key] = [a for a in by_psd.get((p, s, d), []) if d not in fixed_days.get(a, ())]
            if not slots:
                continue
            matched = _max_matching(slots, edges)
            if matched < len(slots):
                issues.append({
                    "type": "daily_capacity", "date": d.isoformat(), "required": len(slots), "assignable": matched,
                    "message": f"{d}: {len(slots)} positions must be filled but at most {matched} can be "
                               f"(one shift per analyst per day)",
                })

    # Weekly working-day capacity across all analysts vs. demand inside the horizon.
    absn = cands.absences
    cand_days: dict[int, set[date]] = defaultdict(set)
    for slot in cands.slots:
        cand_days[slot.analyst_id].add(slot.date)
    ws = week_start(inst.start_date, pol.week_start_day)
    while ws <= inst.end_date:
        days = [ws + timedelta(days=i) for i in range(7)]
        in_h = [d for d in days if inst.start_date <= d <= inst.end_date]
        demand = sum(n for (p, s, d), n in need.items() if d in in_h)
        capacity = 0
        for a in inst.analysts:
            leave = sum(1 for d in days if absn.full_leave_days(a, d))
            n = pol.working_days_per_week
            upper = max(0, n - leave) if pol.leave_counts_as_working_day else min(n, 7 - leave)
            already = sum(1 for d in days if d in fixed_days.get(a, ()))
            capacity += max(0, min(upper - already, len(cand_days[a] & set(in_h))))
        if demand > capacity:
            issues.append({
                "type": "weekly_capacity", "week_start": ws.isoformat(), "required": demand, "capacity": capacity,
                "message": f"Week of {ws}: {demand} analyst-shifts needed but the team can work at most {capacity} "
                           f"under the {pol.working_days_per_week}-day week",
            })
        ws += timedelta(days=7)

    # Locked assignments must be usable and must not clash with each other.
    usable = set(cands.slots)
    for slot in inst.locked:
        if slot in usable:
            continue
        if slot in cands.blocked:
            why = f"blocked by {cands.blocked[slot].kind.replace('_', ' ')}"
        elif (slot.analyst_id, slot.shift_id) in cands.ineligible_reasons:
            why = cands.ineligible_reasons[(slot.analyst_id, slot.shift_id)]
        elif slot.analyst_id not in inst.analysts:
            why = "analyst not included in this run"
        else:
            why = "shift/project not part of this run"
        issues.append({
            "type": "locked_conflict", "analyst_id": slot.analyst_id, "project_id": slot.project_id,
            "shift_id": slot.shift_id, "date": slot.date.isoformat(),
            "message": f"Locked {acode(slot.analyst_id)} {pcode(slot.project_id)}/{scode(slot.shift_id)} on "
                       f"{slot.date} cannot be kept: {why}",
        })
    rest = pol.min_rest_hours * 60
    locked_by_a: dict[int, list[tuple[int, int, Slot]]] = defaultdict(list)
    for slot in [*inst.locked, *inst.fixed]:
        if slot.shift_id in inst.shifts:
            s, e = shift_interval(inst.shifts[slot.shift_id], slot.date)
            locked_by_a[slot.analyst_id].append((s, e, slot))
    fixed_set = set(inst.fixed)
    for a, items in locked_by_a.items():
        items.sort(key=lambda t: t[0])
        for i, (s1, e1, sl1) in enumerate(items):
            for s2, _e2, sl2 in items[i + 1 :]:
                if s2 >= e1 + rest:
                    break
                if sl1 in fixed_set and sl2 in fixed_set:
                    continue
                issues.append({
                    "type": "locked_conflict", "analyst_id": a, "date": sl2.date.isoformat(),
                    "message": f"Locked/fixed shifts for {acode(a)} on {sl1.date} and {sl2.date} overlap or "
                               f"leave less than {pol.min_rest_hours}h rest",
                })

    for a in inst.analysts:
        if not cand_days.get(a):
            entry = {"type": "analyst_unusable", "analyst_id": a,
                     "message": f"{acode(a)} cannot work any shift in this run (eligibility, skills or absences)"}
            if pol.weekly_mode == "exact":
                entry["message"] += "; the exact 5-day rule cannot be met"
                issues.append(entry)
            else:
                warnings.append(entry)

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings + [{"type": "note", "message": n} for n in inst.notes],
        "summary": {
            "analysts": len(inst.analysts),
            "days": len(inst.dates()),
            "required_shift_positions": total_demand,
            "candidate_slots": len(cands.slots),
            "slots_blocked_by_absence": len(cands.blocked),
            "locked": len(inst.locked),
        },
        "disclaimer": "These checks find definite blockers only; the solver makes the final decision.",
    }
