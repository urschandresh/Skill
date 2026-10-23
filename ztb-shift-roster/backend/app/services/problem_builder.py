"""Builds a plain-data ``ProblemInstance`` from the database."""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import Absence, AnalystDef, Policy, ProblemInstance, ProjectDef, ShiftDef, Slot
from ..models import (
    Analyst,
    AnalystProject,
    Assignment,
    AvailabilityException,
    Holiday,
    LeaveRequest,
    Project,
    Roster,
    SchedulingPolicy,
    ShiftTemplate,
)
from ..schemas.scheduling import PolicyFields

DEFAULT_TZ = "Asia/Kolkata"
HISTORY_DAYS = 14


@dataclass
class RunRequest:
    year: int
    month: int
    project_ids: list[int]
    analyst_ids: list[int] | None = None
    policy_id: int | None = None
    policy_overrides: dict = field(default_factory=dict)
    time_limit_seconds: int | None = None
    base_roster_id: int | None = None
    # Regeneration: baseline assignments outside [window_start, window_end] are locked.
    window_start: date | None = None
    window_end: date | None = None
    pending_leave_ids: list[int] = field(default_factory=list)
    exclude_leave_ids: list[int] = field(default_factory=list)
    extra_locked: list[Slot] = field(default_factory=list)


def month_bounds(year: int, month: int) -> tuple[date, date]:
    if not (2000 <= year <= 2100 and 1 <= month <= 12):
        raise HTTPException(status_code=422, detail="year/month out of range")
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def load_policy(session: Session, policy_id: int | None, overrides: dict | None = None) -> tuple[Policy, dict]:
    if policy_id is not None:
        row = session.get(SchedulingPolicy, policy_id)
        if row is None:
            raise HTTPException(status_code=422, detail=f"Policy {policy_id} not found")
    else:
        row = session.scalar(select(SchedulingPolicy).where(SchedulingPolicy.is_default))
        row = row or session.scalar(select(SchedulingPolicy).limit(1))
    base = {k: getattr(row, k) for k in PolicyFields.model_fields if k != "weights"} if row else {}
    base["weights"] = dict(row.weights) if row else {}
    merged = {**base, **(overrides or {})}
    if overrides and "weights" in overrides:
        merged["weights"] = {**base["weights"], **overrides["weights"]}
    validated = PolicyFields.model_validate(merged)  # rejects bad overrides with 422 upstream
    data = validated.model_dump()
    return Policy(**data), {"policy_id": row.id if row else None, "policy_name": row.name if row else None, **data}


def shift_def(t: ShiftTemplate, tz: str) -> ShiftDef:
    return ShiftDef(
        id=t.id, project_id=t.project_id, code=t.code, start_time=t.start_time, end_time=t.end_time,
        is_night=t.is_night, timezone=tz, required_skill_ids=frozenset(s.id for s in t.required_skills),
        active=t.active,
    )


def analyst_def(a: Analyst) -> AnalystDef:
    prefs = a.preferences or {}
    return AnalystDef(
        id=a.id, code=a.employee_code, skill_ids=frozenset(s.id for s in a.skills),
        eligibility={e.project_id: frozenset(e.allowed_shift_codes or ()) for e in a.eligibility},
        max_hours_per_week=a.max_hours_per_week,
        preferred_shifts=frozenset(prefs.get("preferred_shifts", ())),
        avoid_shifts=frozenset(prefs.get("avoid_shifts", ())),
        preferred_off_days=frozenset(prefs.get("preferred_off_days", ())),
    )


def _requirement(rows, d: date) -> tuple[int, int | None]:
    best, rank = None, -1
    for r in rows:
        if r.specific_date is not None:
            if r.specific_date == d and rank < 2:
                best, rank = r, 2
        elif r.weekday is not None:
            if r.weekday == d.weekday() and rank < 1:
                best, rank = r, 1
        elif rank < 0:
            best, rank = r, 0
    return (best.min_staff, best.max_staff) if best else (0, None)


def build_instance(session: Session, req: RunRequest, lenient: bool = False) -> tuple[ProblemInstance, dict]:
    """``lenient`` keeps inactive projects/analysts so stored rosters remain checkable."""
    start, end = month_bounds(req.year, req.month)
    if not req.project_ids:
        raise HTTPException(status_code=422, detail="Select at least one project")
    projects = list(session.scalars(select(Project).where(Project.id.in_(req.project_ids))))
    if len(projects) != len(set(req.project_ids)):
        raise HTTPException(status_code=422, detail="Unknown project id in selection")
    inactive = [p.code for p in projects if not p.active]
    if inactive and not lenient:
        raise HTTPException(status_code=422, detail=f"Inactive projects selected: {inactive}")
    policy, policy_snapshot = load_policy(session, req.policy_id, req.policy_overrides)
    if req.time_limit_seconds:
        policy.solver_time_limit_seconds = req.time_limit_seconds
        policy_snapshot["solver_time_limit_seconds"] = req.time_limit_seconds
    notes: list[str] = []

    project_defs = {p.id: ProjectDef(p.id, p.code, p.timezone, frozenset(s.id for s in p.required_skills))
                    for p in projects}
    tz_of = {p.id: p.timezone for p in projects}
    shifts: dict[int, ShiftDef] = {}
    for p in projects:
        for t in p.shift_templates:
            if t.active or lenient:
                shifts[t.id] = shift_def(t, p.timezone)
    if not shifts:
        raise HTTPException(status_code=422, detail="Selected projects have no active shift templates")

    # Analysts
    if req.analyst_ids is None:
        q = (select(Analyst).join(AnalystProject)
             .where(AnalystProject.project_id.in_(req.project_ids), Analyst.active).distinct())
        analysts = list(session.scalars(q))
    else:
        analysts = list(session.scalars(select(Analyst).where(Analyst.id.in_(req.analyst_ids))))
        if len(analysts) != len(set(req.analyst_ids)):
            raise HTTPException(status_code=422, detail="Unknown analyst id in selection")
    selected = set(req.project_ids)
    usable = []
    for a in analysts:
        if not a.active and not lenient:
            notes.append(f"{a.employee_code} is inactive and was excluded")
        elif not ({e.project_id for e in a.eligibility} & selected):
            notes.append(f"{a.employee_code} is not eligible for any selected project and was excluded")
        else:
            usable.append(a)
    analyst_defs = {a.id: analyst_def(a) for a in usable}
    primary_tz = {}
    for a in usable:
        prim = next((e.project_id for e in a.eligibility if e.is_primary), None)
        primary_tz[a.id] = tz_of.get(prim) or (projects[0].timezone if projects else DEFAULT_TZ)

    # Holidays and staffing
    holidays = list(session.scalars(select(Holiday).where(Holiday.date >= start - timedelta(days=7),
                                                          Holiday.date <= end + timedelta(days=7))))
    blocking = [h for h in holidays if h.blocks_work]
    reqs: dict[tuple[int, int, date], tuple[int, int | None]] = {}
    d = start
    while d <= end:
        for p in projects:
            off = any(h.date == d and h.project_id in (None, p.id) for h in blocking)
            for t in p.shift_templates:
                if t.id not in shifts:
                    continue
                rows = [r for r in p.staffing if r.shift_template_id == t.id]
                reqs[(p.id, t.id, d)] = (0, 0) if off else _requirement(rows, d)
        d += timedelta(days=1)

    # Absences over the full weeks touching the period.
    lo, hi = start - timedelta(days=7), end + timedelta(days=7)
    ids = list(analyst_defs)
    absences: list[Absence] = []
    leave_q = select(LeaveRequest).where(LeaveRequest.analyst_id.in_(ids), LeaveRequest.start_date <= hi,
                                         LeaveRequest.end_date >= lo)
    for lv in session.scalars(leave_q):
        if lv.id in req.exclude_leave_ids:
            continue
        if lv.status != "approved" and lv.id not in req.pending_leave_ids:
            continue
        day = max(lv.start_date, lo)
        while day <= min(lv.end_date, hi):
            if lv.partial_day:
                absences.append(Absence(lv.analyst_id, day, "leave", lv.start_time, lv.end_time,
                                        primary_tz[lv.analyst_id], leave_id=lv.id))
            else:
                absences.append(Absence(lv.analyst_id, day, "leave", leave_id=lv.id))
            day += timedelta(days=1)
    for ex in session.scalars(select(AvailabilityException).where(
            AvailabilityException.analyst_id.in_(ids), AvailabilityException.date >= lo,
            AvailabilityException.date <= hi)):
        if ex.kind == "block_shifts":
            absences.append(Absence(ex.analyst_id, ex.date, "block_shifts", blocked_codes=frozenset(ex.shift_codes)))
        else:
            absences.append(Absence(ex.analyst_id, ex.date, "unavailable"))
    for h in blocking:
        for aid in ids:
            absences.append(Absence(aid, h.date, "holiday", project_id=h.project_id))

    # Fixed assignments: previous-month roster tail and other published rosters this month.
    fixed: list[Slot] = []
    history_from: dict[int, date] = {}
    prev_start, prev_end = month_bounds(*((req.year - 1, 12) if req.month == 1 else (req.year, req.month - 1)))
    prev_rosters = list(session.scalars(select(Roster).where(
        Roster.year == prev_start.year, Roster.month == prev_start.month, Roster.status == "published")))
    if not prev_rosters:
        prev_rosters = list(session.scalars(select(Roster).where(
            Roster.year == prev_start.year, Roster.month == prev_start.month, Roster.status == "historical")
            .order_by(Roster.created_at.desc()).limit(1)))
    for r in prev_rosters:
        covered = set(r.analyst_ids or []) | {a.analyst_id for a in r.assignments} | {m.analyst_id for m in r.markers}
        for aid in covered & set(ids):
            history_from[aid] = prev_start
        for asg in r.assignments:
            if asg.analyst_id in analyst_defs and asg.date >= start - timedelta(days=HISTORY_DAYS):
                fixed.append(Slot(asg.analyst_id, asg.project_id, asg.shift_template_id, asg.date))
    if prev_rosters:
        notes.append(f"Continuity from previous month: {len(prev_rosters)} roster(s), {len(fixed)} assignment(s)")
    else:
        notes.append("No previous-month roster found; month-start rest and weekly rules use only this month")

    others = session.scalars(select(Roster).where(Roster.year == req.year, Roster.month == req.month,
                                                  Roster.status == "published"))
    for r in others:
        if set(r.project_ids or []) & selected or r.id == req.base_roster_id:
            continue  # a version of the roster being produced, not an independent commitment
        n = 0
        for asg in r.assignments:
            if asg.analyst_id in analyst_defs:
                fixed.append(Slot(asg.analyst_id, asg.project_id, asg.shift_template_id, asg.date))
                n += 1
        if n:
            notes.append(f"{n} assignment(s) from published roster '{r.name}' (other projects) are kept fixed")

    for slot in fixed:  # make sure the solver/validator know the timings of referenced shifts
        if slot.shift_id not in shifts:
            t = session.get(ShiftTemplate, slot.shift_id)
            if t is not None:
                tz = session.get(Project, t.project_id).timezone
                shifts[t.id] = shift_def(t, tz)
    fixed = [f for f in fixed if f.shift_id in shifts]

    # Baseline and locks (regeneration).
    locked: list[Slot] = list(req.extra_locked)
    baseline: list[Slot] = []
    if req.base_roster_id is not None:
        base = session.get(Roster, req.base_roster_id)
        if base is None or (base.year, base.month) != (req.year, req.month):
            raise HTTPException(status_code=422, detail="Base roster does not match the selected month")
        for asg in base.assignments:
            slot = Slot(asg.analyst_id, asg.project_id, asg.shift_template_id, asg.date)
            if asg.project_id not in selected or asg.analyst_id not in analyst_defs:
                continue
            baseline.append(slot)
            outside = req.window_start is not None and not (req.window_start <= asg.date <= (req.window_end or end))
            if asg.locked or outside:
                locked.append(slot)
    locked = sorted(set(locked))

    inst = ProblemInstance(
        start_date=start, end_date=end, projects=project_defs, shifts=shifts, analysts=analyst_defs,
        requirements=reqs, absences=absences, locked=locked, fixed=fixed, history_known_from=history_from,
        baseline=baseline, policy=policy, notes=notes,
    )
    return inst, policy_snapshot


def instance_for_roster(session: Session, roster: Roster, pending_leave_ids: list[int] | None = None,
                        exclude_leave_ids: list[int] | None = None) -> ProblemInstance:
    """The problem a stored roster must satisfy, using today's leave and settings."""
    snapshot = dict(roster.policy_snapshot or {})
    overrides = {k: v for k, v in snapshot.items() if k in PolicyFields.model_fields}
    analyst_ids = roster.analyst_ids or sorted({a.analyst_id for a in roster.assignments})
    existing = set(session.scalars(select(Analyst.id).where(Analyst.id.in_(analyst_ids))))
    req = RunRequest(
        year=roster.year, month=roster.month, project_ids=list(roster.project_ids or []),
        analyst_ids=[a for a in analyst_ids if a in existing], policy_id=snapshot.get("policy_id")
        if snapshot.get("policy_id") and session.get(SchedulingPolicy, snapshot["policy_id"]) else None,
        policy_overrides=overrides, pending_leave_ids=pending_leave_ids or [],
        exclude_leave_ids=exclude_leave_ids or [],
    )
    inst, _ = build_instance(session, req, lenient=True)
    inst.locked = sorted(Slot(a.analyst_id, a.project_id, a.shift_template_id, a.date)
                         for a in roster.assignments if a.locked)
    for a in roster.assignments:  # timings for any template no longer active
        if a.shift_template_id not in inst.shifts and a.shift_template:
            inst.shifts[a.shift_template_id] = shift_def(a.shift_template, a.project.timezone)
    others = [f for f in inst.fixed if not (roster.year == f.date.year and roster.month == f.date.month
                                            and f.project_id in set(roster.project_ids or []))]
    inst.fixed = others
    return inst
