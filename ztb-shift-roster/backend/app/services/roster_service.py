"""Roster generation jobs, versions, grid views, validated edits and publishing."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import asdict
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from ..domain import Slot
from ..models import (
    Analyst,
    Assignment,
    Holiday,
    LeaveRequest,
    Project,
    Roster,
    ShiftTemplate,
    SolverRun,
    utcnow,
)
from ..solver.feasibility import preliminary_check
from ..solver.model import solve
from ..validators.roster_validator import validate_roster
from .audit import record
from .jobs import JobHandle, JobManager
from .problem_builder import (
    RunRequest,
    analyst_def,
    build_instance,
    instance_for_roster,
    month_bounds,
    shift_def,
)

# --------------------------------------------------------------------------- generation


def _request_to_params(req: RunRequest) -> dict:
    data = asdict(req)
    data["window_start"] = req.window_start.isoformat() if req.window_start else None
    data["window_end"] = req.window_end.isoformat() if req.window_end else None
    data["extra_locked"] = [[s.analyst_id, s.project_id, s.shift_id, s.date.isoformat()] for s in req.extra_locked]
    return data


def _params_to_request(params: dict) -> RunRequest:
    p = dict(params)
    p["window_start"] = date.fromisoformat(p["window_start"]) if p.get("window_start") else None
    p["window_end"] = date.fromisoformat(p["window_end"]) if p.get("window_end") else None
    p["extra_locked"] = [Slot(a, pr, s, date.fromisoformat(d)) for a, pr, s, d in p.get("extra_locked", [])]
    return RunRequest(**p)


def start_run(session: Session, jobs: JobManager, factory: sessionmaker, req: RunRequest, kind: str,
              max_seconds: int) -> SolverRun:
    """Validate the request synchronously (bad input fails fast with 422), then queue the solve."""
    build_instance(session, req)
    limit = req.time_limit_seconds
    if limit is not None and not 1 <= limit <= max_seconds:
        raise HTTPException(status_code=422, detail=f"time_limit_seconds must be between 1 and {max_seconds}")
    run = SolverRun(id=str(uuid.uuid4()), kind=kind, state="queued", year=req.year, month=req.month,
                    base_roster_id=req.base_roster_id, params=_request_to_params(req))
    session.add(run)
    record(session, "queue_run", "solver_run", run.id, kind=kind)
    session.commit()
    jobs.submit(run.id, lambda handle: _execute_run(factory, run.id, handle))
    return run


def _execute_run(factory: sessionmaker, run_id: str, handle: JobHandle) -> None:
    with factory() as session:
        run = session.get(SolverRun, run_id)
        req = _params_to_request(run.params)
        handle.report(phase="preparing")
        inst, policy_snapshot = build_instance(session, req)
        pre = preliminary_check(inst)
        result: dict = {"preliminary": pre, "notes": inst.notes}
        if not pre["ok"]:
            run.solver_status = "INFEASIBLE"
            run.state = "completed"
            result.update(status="INFEASIBLE", proven_by="preliminary_check", diagnostics=pre["issues"],
                          message="Hard constraints cannot all be met (found before solving).")
            run.result = result
            run.message = result["message"]
            run.finished_at = utcnow()
            session.commit()
            return

        res = solve(inst, handle=handle)
        result.update(
            status=res.status, message=res.message, objective=res.objective, best_bound=res.best_bound,
            wall_time_seconds=res.wall_time, solutions_found=res.solutions_found,
            stopped_by_user=res.stopped_by_user, diagnostics=res.diagnostics,
            objective_breakdown=res.objective_breakdown, model_stats=res.model_stats,
        )
        run.solver_status = res.status
        run.message = res.message
        if res.has_solution:
            handle.report(phase="validating")
            report = validate_roster(inst, res.assignments)
            result["validation"] = report.to_dict()
            if not report.is_valid:
                # Never present an unverified roster as valid.
                run.solver_status = "ERROR"
                run.state = "failed"
                run.message = "Solver output failed independent validation; roster not saved."
                result["status"] = "ERROR"
                result["message"] = run.message
            elif run.kind == "simulate":
                result["assignments"] = [[s.analyst_id, s.project_id, s.shift_id, s.date.isoformat()]
                                         for s in res.assignments]
                base = set(inst.baseline)
                new = set(res.assignments)
                result["changes"] = {"removed": len(base - new), "added": len(new - base)}
                run.state = "completed"
            else:
                roster = _save_generated(session, run, req, inst, res, policy_snapshot, report)
                run.roster_id = roster.id
                run.state = "completed"
        else:
            run.state = "cancelled" if res.status == "CANCELLED" else "completed"
        run.result = result
        run.finished_at = utcnow()
        session.commit()


def next_version(session: Session, year: int, month: int) -> int:
    return (session.scalar(select(func.max(Roster.version)).where(Roster.year == year, Roster.month == month)) or 0) + 1


def _save_generated(session, run, req, inst, res, policy_snapshot, report) -> Roster:
    version = next_version(session, req.year, req.month)
    base = session.get(Roster, req.base_roster_id) if req.base_roster_id else None
    base_meta: dict[Slot, tuple[str, str | None, bool]] = {}
    if base is not None:
        for a in base.assignments:
            base_meta[Slot(a.analyst_id, a.project_id, a.shift_template_id, a.date)] = (
                a.source, a.override_reason, a.locked)
    user_locks = set(req.extra_locked)
    roster = Roster(
        year=req.year, month=req.month, status="draft", version=version,
        name=f"{req.year}-{req.month:02d} v{version}" + (" (regenerated)" if base else ""),
        parent_roster_id=req.base_roster_id, project_ids=sorted(req.project_ids),
        analyst_ids=sorted(inst.analysts), policy_snapshot=policy_snapshot, solver_status=res.status,
        solver_summary={"run_id": run.id, "objective": res.objective, "best_bound": res.best_bound,
                        "wall_time_seconds": res.wall_time, "coverage_percent": report.to_dict()["coverage_percent"]},
    )
    session.add(roster)
    session.flush()
    for s in res.assignments:
        # Keep the user's own locks; window-derived locks only constrained this solve.
        source, reason, was_locked = base_meta.get(s, ("solver", None, False))
        session.add(Assignment(roster_id=roster.id, analyst_id=s.analyst_id, project_id=s.project_id,
                               shift_template_id=s.shift_id, date=s.date, locked=was_locked or s in user_locks,
                               source=source, override_reason=reason))
    record(session, "generate", "roster", roster.id, run_id=run.id, assignments=len(res.assignments))
    return roster


def job_view(run: SolverRun, jobs: JobManager) -> dict:
    handle = jobs.get(run.id)
    live = handle.progress() if handle is not None and run.state in ("queued", "running") else {}
    return {
        "id": run.id, "kind": run.kind, "state": run.state, "solver_status": run.solver_status,
        "roster_id": run.roster_id, "base_roster_id": run.base_roster_id, "year": run.year, "month": run.month,
        "message": run.message, "created_at": run.created_at, "started_at": run.started_at,
        "finished_at": run.finished_at, "progress": live, "result": run.result or {},
        "time_limit_seconds": (run.params or {}).get("time_limit_seconds"),
    }


# --------------------------------------------------------------------------- views


def roster_summary(r: Roster) -> dict:
    return {
        "id": r.id, "year": r.year, "month": r.month, "name": r.name, "status": r.status, "version": r.version,
        "parent_roster_id": r.parent_roster_id, "project_ids": r.project_ids, "analyst_ids": r.analyst_ids,
        "solver_status": r.solver_status, "solver_summary": r.solver_summary, "notes": r.notes,
        "created_at": r.created_at, "updated_at": r.updated_at, "published_at": r.published_at,
        "assignment_count": len(r.assignments), "locked_count": sum(1 for a in r.assignments if a.locked),
    }


def assignment_dict(a: Assignment) -> dict:
    return {"id": a.id, "analyst_id": a.analyst_id, "project_id": a.project_id,
            "shift_template_id": a.shift_template_id, "date": a.date.isoformat(), "locked": a.locked,
            "source": a.source, "override_reason": a.override_reason}


def roster_detail(session: Session, roster: Roster) -> dict:
    start, end = month_bounds(roster.year, roster.month)
    analyst_ids = sorted(set(roster.analyst_ids or []) | {a.analyst_id for a in roster.assignments}
                         | {m.analyst_id for m in roster.markers})
    analysts = {a.id: a for a in session.scalars(select(Analyst).where(Analyst.id.in_(analyst_ids)))}
    leaves = list(session.scalars(select(LeaveRequest).where(
        LeaveRequest.analyst_id.in_(analyst_ids), LeaveRequest.start_date <= end, LeaveRequest.end_date >= start,
        LeaveRequest.status.in_(("approved", "pending")))))
    holidays = list(session.scalars(select(Holiday).where(Holiday.date >= start, Holiday.date <= end)))
    markers = {(m.analyst_id, m.date): m.code for m in roster.markers}
    by_cell: dict[tuple[int, date], list[dict]] = defaultdict(list)
    for a in roster.assignments:
        by_cell[(a.analyst_id, a.date)].append(assignment_dict(a))
    leave_cells: dict[tuple[int, date], dict] = {}
    for lv in leaves:
        d = max(lv.start_date, start)
        while d <= min(lv.end_date, end):
            leave_cells[(lv.analyst_id, d)] = {"leave_id": lv.id, "status": lv.status, "partial": lv.partial_day,
                                               "type": lv.leave_type}
            d += timedelta(days=1)
    rows = []
    for aid in analyst_ids:
        a = analysts.get(aid)
        cells = {}
        d = start
        while d <= end:
            items = by_cell.get((aid, d), [])
            leave = leave_cells.get((aid, d))
            hol = next((h for h in holidays if h.date == d), None)
            if items:
                marker = None
            elif leave and leave["status"] == "approved" and not leave["partial"]:
                marker = "LEAVE"
            elif (aid, d) in markers:
                marker = markers[(aid, d)]
            elif hol is not None and hol.blocks_work:
                marker = "H"
            else:
                marker = "WO"
            cells[d.isoformat()] = {"assignments": items, "marker": marker, "leave": leave,
                                    "holiday": hol.name if hol else None}
            d += timedelta(days=1)
        rows.append({"analyst_id": aid, "employee_code": a.employee_code if a else f"#{aid}",
                     "full_name": a.full_name if a else "(deleted)", "cells": cells})
    project_ids = set(roster.project_ids or []) | {a.project_id for a in roster.assignments}
    projects = list(session.scalars(select(Project).where(Project.id.in_(project_ids))))
    templates = list(session.scalars(select(ShiftTemplate).where(ShiftTemplate.project_id.in_(project_ids))))
    return {
        **roster_summary(roster),
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "assignments": [assignment_dict(a) for a in roster.assignments],
        "rows": rows,
        "projects": [{"id": p.id, "code": p.code, "name": p.name} for p in projects],
        "shift_templates": [{"id": t.id, "project_id": t.project_id, "code": t.code, "name": t.name,
                             "start_time": t.start_time, "end_time": t.end_time, "is_night": t.is_night,
                             "color": t.color, "active": t.active} for t in templates],
        "holidays": [{"date": h.date.isoformat(), "name": h.name, "blocks_work": h.blocks_work} for h in holidays],
    }


def validate_stored(session: Session, roster: Roster, pending_leave_ids: list[int] | None = None):
    inst = instance_for_roster(session, roster, pending_leave_ids)
    slots = [Slot(a.analyst_id, a.project_id, a.shift_template_id, a.date) for a in roster.assignments]
    return inst, validate_roster(inst, slots)


# --------------------------------------------------------------------------- edits


def _vkey(v) -> tuple:
    return (v.rule, v.analyst_id, v.project_id, v.shift_id, v.date, v.message)


def apply_changes(session: Session, roster: Roster, ops: list[dict], dry_run: bool,
                  override_reason: str | None) -> dict:
    if roster.status != "draft":
        raise HTTPException(status_code=409, detail="Only draft rosters can be edited; create a new version first")
    inst = instance_for_roster(session, roster)
    current = {Slot(a.analyst_id, a.project_id, a.shift_template_id, a.date): a for a in roster.assignments}
    before = validate_roster(inst, list(current))
    proposed: dict[Slot, dict] = {s: {"locked": a.locked, "source": a.source, "override_reason": a.override_reason}
                                  for s, a in current.items()}

    def slot_of(d: dict, prefix: str = "") -> Slot:
        return Slot(int(d[prefix + "analyst_id"]), int(d[prefix + "project_id"]),
                    int(d[prefix + "shift_template_id"]), date.fromisoformat(str(d[prefix + "date"])))

    for op in ops:
        kind = op["op"]
        if kind == "add":
            s = slot_of(op)
            tpl = session.get(ShiftTemplate, s.shift_id)
            if tpl is None or tpl.project_id != s.project_id or session.get(Analyst, s.analyst_id) is None:
                raise HTTPException(status_code=422, detail="add: unknown analyst, project or shift template")
            if s in proposed:
                raise HTTPException(status_code=409, detail="add: assignment already exists")
            proposed[s] = {"locked": bool(op.get("locked", False)), "source": "manual", "override_reason": None}
        elif kind == "remove":
            s = slot_of(op)
            if s not in proposed:
                raise HTTPException(status_code=404, detail="remove: assignment not found")
            if proposed[s]["locked"]:
                raise HTTPException(status_code=409, detail="remove: assignment is locked; unlock it first")
            del proposed[s]
        elif kind == "move":
            src, dst = slot_of(op, "from_"), slot_of(op, "to_")
            if src not in proposed:
                raise HTTPException(status_code=404, detail="move: source assignment not found")
            if proposed[src]["locked"]:
                raise HTTPException(status_code=409, detail="move: assignment is locked; unlock it first")
            tpl = session.get(ShiftTemplate, dst.shift_id)
            if tpl is None or tpl.project_id != dst.project_id or session.get(Analyst, dst.analyst_id) is None:
                raise HTTPException(status_code=422, detail="move: unknown target analyst, project or shift")
            if dst in proposed and dst != src:
                raise HTTPException(status_code=409, detail="move: target assignment already exists")
            meta = proposed.pop(src)
            proposed[dst] = {**meta, "source": "manual"}
        elif kind in ("lock", "unlock"):
            s = slot_of(op)
            if s not in proposed:
                raise HTTPException(status_code=404, detail=f"{kind}: assignment not found")
            proposed[s]["locked"] = kind == "lock"
        else:  # pragma: no cover - schema prevents this
            raise HTTPException(status_code=422, detail=f"unknown op {kind}")

    for s in proposed:  # analysts/shifts added by hand that the stored roster did not include
        if s.analyst_id not in inst.analysts:
            inst.analysts[s.analyst_id] = analyst_def(session.get(Analyst, s.analyst_id))
        if s.shift_id not in inst.shifts:
            t = session.get(ShiftTemplate, s.shift_id)
            inst.shifts[t.id] = shift_def(t, t.project.timezone)
    inst.locked = sorted(s for s, m in proposed.items() if m["locked"])
    after = validate_roster(inst, list(proposed))
    before_keys = {_vkey(v) for v in before.errors}
    after_keys = {_vkey(v) for v in after.errors}
    introduced = [v.to_dict() for v in after.errors if _vkey(v) not in before_keys]
    resolved = [v.to_dict() for v in before.errors if _vkey(v) not in after_keys]
    response = {"dry_run": dry_run, "introduced": introduced, "resolved": resolved,
                "validation": after.to_dict(), "committed": False}
    if dry_run:
        return response
    if introduced and not override_reason:
        raise HTTPException(status_code=409, detail={
            "message": "The change breaks hard rules. Fix it or confirm with an override reason.",
            "introduced": introduced})

    for s, a in current.items():
        if s not in proposed:
            session.delete(a)
    session.flush()
    for s, meta in proposed.items():
        if s in current:
            current[s].locked = meta["locked"]
        else:
            session.add(Assignment(roster_id=roster.id, analyst_id=s.analyst_id, project_id=s.project_id,
                                   shift_template_id=s.shift_id, date=s.date, locked=meta["locked"],
                                   source="manual", override_reason=override_reason if introduced else None))
    if roster.analyst_ids is not None:
        roster.analyst_ids = sorted(set(roster.analyst_ids) | {s.analyst_id for s in proposed})
    roster.updated_at = utcnow()
    record(session, "edit", "roster", roster.id, ops=len(ops), introduced=len(introduced),
           override=bool(introduced and override_reason))
    session.commit()
    response["committed"] = True
    return response


def publish(session: Session, roster: Roster, override_reason: str | None) -> dict:
    if roster.status != "draft":
        raise HTTPException(status_code=409, detail="Only a draft roster can be published")
    _inst, report = validate_stored(session, roster)
    if not report.is_valid and not override_reason:
        raise HTTPException(status_code=409, detail={
            "message": f"Roster has {len(report.errors)} rule violation(s); publish requires an override reason.",
            "validation": report.to_dict()})
    for other in session.scalars(select(Roster).where(Roster.year == roster.year, Roster.month == roster.month,
                                                      Roster.status == "published")):
        if set(other.project_ids or []) & set(roster.project_ids or []):
            other.status = "archived"
    roster.status = "published"
    roster.published_at = utcnow()
    if override_reason:
        roster.notes = (roster.notes + "\n" if roster.notes else "") + f"Published with violations: {override_reason}"
    record(session, "publish", "roster", roster.id, violations=len(report.errors))
    session.commit()
    return report.to_dict()


def clone(session: Session, roster: Roster) -> Roster:
    version = next_version(session, roster.year, roster.month)
    copy = Roster(year=roster.year, month=roster.month, status="draft", version=version,
                  name=f"{roster.year}-{roster.month:02d} v{version}", parent_roster_id=roster.id,
                  project_ids=list(roster.project_ids or []), analyst_ids=list(roster.analyst_ids or []),
                  policy_snapshot=dict(roster.policy_snapshot or {}), solver_status=roster.solver_status,
                  solver_summary=dict(roster.solver_summary or {}))
    session.add(copy)
    session.flush()
    for a in roster.assignments:
        session.add(Assignment(roster_id=copy.id, analyst_id=a.analyst_id, project_id=a.project_id,
                               shift_template_id=a.shift_template_id, date=a.date, locked=a.locked,
                               source=a.source, override_reason=a.override_reason))
    record(session, "clone", "roster", copy.id, source=roster.id)
    session.commit()
    session.refresh(copy)
    return copy
