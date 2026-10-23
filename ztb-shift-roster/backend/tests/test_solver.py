"""CP-SAT engine tests on SYNTHETIC instances, each result re-checked by the independent validator."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from app.domain import Absence, AnalystDef, Policy, Slot
from app.services.jobs import JobHandle
from app.solver.feasibility import preliminary_check
from app.solver.model import solve
from app.validators.roster_validator import validate_roster

from .synthetic import make_instance


def solved(inst, limit=20):
    r = solve(inst, time_limit=limit)
    assert r.status in ("OPTIMAL", "FEASIBLE"), (r.status, r.message, r.diagnostics)
    report = validate_roster(inst, r.assignments)
    assert report.is_valid, [v.message for v in report.errors][:10]
    return r, report


def test_valid_month_roster_meets_every_rule():
    inst = make_instance()
    r, report = solved(inst)
    cov = Counter((s.shift_id, s.date) for s in r.assignments)
    for (p, s, d), (mn, _) in inst.requirements.items():
        assert cov[(s, d)] >= mn
    # Exactly five days in every week fully inside November 2026 (Mon 2nd .. Sun 29th).
    for a in inst.analysts:
        for k in range(4):
            ws = date(2026, 11, 2) + timedelta(days=7 * k)
            worked = {s.date for s in r.assignments if s.analyst_id == a and ws <= s.date < ws + timedelta(days=7)}
            assert len(worked) == 5
    nights = [m["nights"] for m in report.metrics.values()]
    assert max(nights) - min(nights) <= 1
    weekends = [m["weekend_shifts"] for m in report.metrics.values()]
    assert max(weekends) - min(weekends) <= 1


def test_insufficient_headcount_is_infeasible_with_diagnostics():
    inst = make_instance(n_analysts=3)
    pre = preliminary_check(inst)
    assert not pre["ok"]
    assert any(i["type"] == "weekly_capacity" for i in pre["issues"])
    r = solve(inst, time_limit=10)
    assert r.status == "INFEASIBLE"
    assert r.assignments == []
    assert r.diagnostics and all("type" in d for d in r.diagnostics)
    assert {d["type"] for d in r.diagnostics} & {"coverage", "weekly_days", "consecutive_days"}


def test_approved_leave_blocks_assignment():
    inst = make_instance()
    leave_days = [date(2026, 11, d) for d in range(9, 14)]
    inst.absences = [Absence(100, d, "leave") for d in leave_days]
    r, report = solved(inst)
    assert not [s for s in r.assignments if s.analyst_id == 100 and s.date in leave_days]
    # Leave consumes working days: Mon 9 - Fri 13 is the whole working week for analyst 100.
    assert not [s for s in r.assignments if s.analyst_id == 100 and date(2026, 11, 9) <= s.date <= date(2026, 11, 15)]
    assert report.metrics[100]["leave_days"] == 5


def test_partial_day_leave_blocks_only_overlapping_shifts():
    inst = make_instance(days=7)
    inst.absences = [Absence(100, date(2026, 11, 3), "leave", start_time="05:00", end_time="10:00")]
    r, _ = solved(inst)
    on_day = [s for s in r.assignments if s.analyst_id == 100 and s.date == date(2026, 11, 3)]
    assert all(inst.shifts[s.shift_id].code != "M" for s in on_day)
    # The night shift of Nov 2 runs until 07:00 on Nov 3, inside the leave window.
    assert not [s for s in r.assignments if s.analyst_id == 100 and s.date == date(2026, 11, 2)
                and inst.shifts[s.shift_id].code == "N"]


def test_cross_project_analyst_never_double_booked():
    inst = make_instance(n_analysts=12, n_projects=2, shared_analysts=True, days=14)
    r, _ = solved(inst)
    per_day = Counter((s.analyst_id, s.date) for s in r.assignments)
    assert max(per_day.values()) == 1
    assert {s.project_id for s in r.assignments} == {1, 2}


def test_cross_project_overlap_detected_by_validator():
    inst = make_instance(n_analysts=2, n_projects=2, shared_analysts=True, days=3)
    bad = [Slot(100, 1, 10, date(2026, 11, 2)), Slot(100, 2, 20, date(2026, 11, 2))]
    rules = {v.rule for v in validate_roster(inst, bad).errors}
    assert "overlap" in rules and "one_shift_per_day" in rules


def test_min_rest_and_overnight_handling_in_validator():
    inst = make_instance(days=5)
    night_then_morning = [Slot(100, 1, 12, date(2026, 11, 2)), Slot(100, 1, 10, date(2026, 11, 3))]
    errs = validate_roster(inst, night_then_morning).errors
    assert any(v.rule == "overlap" for v in errs)  # N ends 07:00, M starts 06:00 next day
    afternoon_then_morning = [Slot(100, 1, 11, date(2026, 11, 2)), Slot(100, 1, 10, date(2026, 11, 3))]
    errs = validate_roster(inst, afternoon_then_morning).errors
    assert any(v.rule == "min_rest" and "7.0h" in v.message for v in errs)
    night_then_night = [Slot(100, 1, 12, date(2026, 11, 2)), Slot(100, 1, 12, date(2026, 11, 3))]
    assert not [v for v in validate_roster(inst, night_then_night).errors if v.rule in ("min_rest", "overlap")]


def test_solver_respects_min_rest_policy():
    inst = make_instance(days=14)
    r, _ = solved(inst)
    by_a = {}
    for s in r.assignments:
        by_a.setdefault(s.analyst_id, {})[s.date] = inst.shifts[s.shift_id].code
    forbidden = {("A", "M"), ("N", "M"), ("N", "A")}
    for days in by_a.values():
        for d, code in days.items():
            nxt = days.get(d + timedelta(days=1))
            assert (code, nxt) not in forbidden


def test_consecutive_night_limit():
    inst = make_instance(policy=Policy(max_consecutive_nights=2))
    r, _ = solved(inst)
    for a in inst.analysts:
        nights = sorted(s.date for s in r.assignments if s.analyst_id == a and inst.shifts[s.shift_id].is_night)
        run = longest = 0
        prev = None
        for d in nights:
            run = run + 1 if prev and d - prev == timedelta(days=1) else 1
            longest = max(longest, run)
            prev = d
        assert longest <= 2
    seq = [Slot(100, 1, 12, date(2026, 11, d)) for d in (2, 3, 4)]
    assert any(v.rule == "consecutive_nights" for v in validate_roster(inst, seq).errors)


def test_month_boundary_continuity():
    inst = make_instance(days=10, policy=Policy(max_consecutive_work_days=5))
    # Previous month: analyst 100 worked nights Oct 27-31 (5 in a row, the limit).
    inst.history_known_from = {100: date(2026, 10, 18)}
    inst.fixed = [Slot(100, 1, 12, date(2026, 10, d)) for d in range(27, 32)]
    r, report = solved(inst)
    nov1 = [s for s in r.assignments if s.analyst_id == 100 and s.date == date(2026, 11, 1)]
    assert nov1 == []  # a sixth consecutive day is not allowed
    # Week Mon Oct 26 - Sun Nov 1 already has 5 worked days for analyst 100.
    assert report.is_valid
    bad = [Slot(100, 1, 10, date(2026, 11, 1))]
    rules = {v.rule for v in validate_roster(inst, bad, check_locks=False).errors}
    assert {"overlap", "consecutive_days", "weekly_days"} <= rules


def test_boundary_week_inherited_shortfall_is_explicit_warning():
    inst = make_instance(days=7)
    # Analyst 100 worked only Oct 26-27 in the boundary week; Nov 1 alone cannot reach 5 days.
    inst.history_known_from = {100: date(2026, 10, 1)}
    inst.fixed = [Slot(100, 1, 10, date(2026, 10, 26)), Slot(100, 1, 10, date(2026, 10, 27))]
    r, report = solved(inst)
    warn = [v for v in report.violations if v.rule == "weekly_days_inherited" and v.analyst_id == 100]
    assert warn and warn[0].severity == "warning"
    assert [s for s in r.assignments if s.analyst_id == 100 and s.date == date(2026, 11, 1)]


def test_locked_assignments_are_kept():
    inst = make_instance(days=14)
    locks = [Slot(103, 1, 12, date(2026, 11, 4)), Slot(105, 1, 10, date(2026, 11, 10))]
    inst.locked = locks
    r, _ = solved(inst)
    assert set(locks) <= set(r.assignments)


def test_lock_conflicting_with_leave_is_reported_not_dropped():
    inst = make_instance(days=7)
    inst.absences = [Absence(103, date(2026, 11, 4), "leave")]
    inst.locked = [Slot(103, 1, 12, date(2026, 11, 4))]
    pre = preliminary_check(inst)
    assert any(i["type"] == "locked_conflict" for i in pre["issues"])
    r = solve(inst, time_limit=10)
    assert r.status == "INFEASIBLE"
    assert any(d["type"] == "locked" for d in r.diagnostics)


def test_skill_and_shift_eligibility():
    inst = make_instance(n_analysts=8, days=7)
    # Analyst 100 may only work mornings; analyst 101 lacks the skill the night shift needs.
    a100 = inst.analysts[100]
    inst.analysts[100] = AnalystDef(100, a100.code, frozenset(), {1: frozenset({"M"})})
    from dataclasses import replace
    inst.shifts[12] = replace(inst.shifts[12], required_skill_ids=frozenset({7}))
    for aid in range(102, 108):
        a = inst.analysts[aid]
        inst.analysts[aid] = replace(a, skill_ids=frozenset({7}))
    r, _ = solved(inst)
    assert {inst.shifts[s.shift_id].code for s in r.assignments if s.analyst_id == 100} <= {"M"}
    assert not [s for s in r.assignments if s.analyst_id == 101 and s.shift_id == 12]


def test_minimum_disruption_regeneration():
    inst = make_instance()
    base, _ = solved(inst)
    inst.baseline = list(base.assignments)
    leave = [date(2026, 11, 16), date(2026, 11, 17)]
    inst.absences = [Absence(100, d, "leave") for d in leave]
    r, _ = solved(inst, limit=30)
    changed = len(set(base.assignments) ^ set(r.assignments))
    # Only the area around the leave should move, not the whole month.
    assert changed <= 30, changed
    assert not [s for s in r.assignments if s.analyst_id == 100 and s.date in leave]


def test_timeout_status_is_reported_honestly():
    inst = make_instance(n_analysts=60, n_projects=6, days=31, shared_analysts=True, min_staff=2)
    r = solve(inst, time_limit=0.05)
    assert r.status in ("TIMEOUT", "FEASIBLE", "OPTIMAL")
    if r.status == "TIMEOUT":
        assert r.assignments == [] and "time" in r.message.lower()
    else:
        assert validate_roster(inst, r.assignments).is_valid


def test_cancel_before_start():
    handle = JobHandle("t")
    handle.cancel()
    r = solve(make_instance(days=7), time_limit=30, handle=handle)
    assert r.status == "CANCELLED" and r.stopped_by_user and r.assignments == []


def test_cancel_during_search_stops_quickly():
    import threading
    import time

    inst = make_instance(n_analysts=40, n_projects=4, days=31, shared_analysts=True, min_staff=2)
    handle = JobHandle("t")
    handle.started_monotonic = time.monotonic()
    timer = threading.Timer(3.0, handle.cancel)
    timer.start()
    r = solve(inst, time_limit=120, handle=handle)
    timer.cancel()
    assert r.stopped_by_user
    assert r.status in ("CANCELLED", "FEASIBLE")
    assert r.wall_time < 30
    if r.status == "FEASIBLE":
        assert validate_roster(inst, r.assignments).is_valid


def test_max_weekly_mode_and_hours_cap():
    inst = make_instance(days=14, policy=Policy(weekly_mode="max", max_hours_per_week=36))
    r, _ = solved(inst)
    for a in inst.analysts:
        for ws in (date(2026, 11, 2), date(2026, 11, 9)):
            n = sum(1 for s in r.assignments if s.analyst_id == a and ws <= s.date < ws + timedelta(days=7))
            assert n <= 4  # 36h cap / 9h shifts


def test_coverage_shortfall_flagged_by_validator():
    inst = make_instance(days=2)
    report = validate_roster(inst, [Slot(100, 1, 10, date(2026, 11, 1))], check_locks=False)
    cov = [v for v in report.errors if v.rule == "coverage"]
    assert len(cov) == 5  # 6 shift-days, one covered
    assert report.to_dict()["coverage_percent"] < 20
