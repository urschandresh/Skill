"""Roster generation, versions, validation, manual edits and publishing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import Slot
from ..models import Roster, SolverRun
from ..schemas.roster import ChangesIn, GenerateIn, PublishIn, RegenerateIn, RosterPatch
from ..services import roster_service as svc
from ..services.audit import record
from ..services.problem_builder import RunRequest, build_instance
from ..solver.feasibility import preliminary_check
from .deps import get_db, get_or_404

router = APIRouter(tags=["rosters"])


def _run_request(body: GenerateIn) -> RunRequest:
    return RunRequest(
        year=body.year, month=body.month, project_ids=body.project_ids, analyst_ids=body.analyst_ids,
        policy_id=body.policy_id, policy_overrides=body.policy_overrides.as_dict(),
        time_limit_seconds=body.time_limit_seconds, pending_leave_ids=body.simulate_pending_leave_ids,
        extra_locked=[Slot(s.analyst_id, s.project_id, s.shift_template_id, s.date) for s in body.locked],
    )


@router.post("/rosters/feasibility")
def feasibility(body: GenerateIn, db: Session = Depends(get_db)):
    inst, policy = build_instance(db, _run_request(body))
    return {**preliminary_check(inst), "policy": policy}


@router.post("/rosters/generate", status_code=202)
def generate(body: GenerateIn, request: Request, db: Session = Depends(get_db)):
    st = request.app.state
    kind = "simulate" if body.simulate_pending_leave_ids else "generate"
    run = svc.start_run(db, st.jobs, st.session_factory, _run_request(body), kind, st.settings.max_solver_seconds)
    return {"run_id": run.id, "state": run.state}


@router.get("/rosters")
def list_rosters(year: int | None = None, month: int | None = None, status: str | None = None,
                 db: Session = Depends(get_db)):
    q = select(Roster).order_by(Roster.year.desc(), Roster.month.desc(), Roster.version.desc())
    if year is not None:
        q = q.where(Roster.year == year)
    if month is not None:
        q = q.where(Roster.month == month)
    if status is not None:
        q = q.where(Roster.status == status)
    return [svc.roster_summary(r) for r in db.scalars(q)]


@router.get("/rosters/{roster_id}")
def get_roster(roster_id: int, db: Session = Depends(get_db)):
    return svc.roster_detail(db, get_or_404(db, Roster, roster_id))


@router.patch("/rosters/{roster_id}")
def patch_roster(roster_id: int, body: RosterPatch, db: Session = Depends(get_db)):
    roster = get_or_404(db, Roster, roster_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(roster, k, v)
    db.commit()
    return svc.roster_summary(roster)


@router.delete("/rosters/{roster_id}", status_code=204)
def delete_roster(roster_id: int, db: Session = Depends(get_db)):
    roster = get_or_404(db, Roster, roster_id)
    if roster.status in ("published", "archived"):
        raise HTTPException(status_code=409, detail="Published and archived rosters are kept for the record")
    db.delete(roster)
    record(db, "delete", "roster", roster_id)
    db.commit()
    return Response(status_code=204)


@router.get("/rosters/{roster_id}/validation")
def validate(roster_id: int, db: Session = Depends(get_db)):
    _inst, report = svc.validate_stored(db, get_or_404(db, Roster, roster_id))
    return {**report.to_dict(), "coverage": report.coverage}


@router.post("/rosters/{roster_id}/changes")
def changes(roster_id: int, body: ChangesIn, db: Session = Depends(get_db)):
    roster = get_or_404(db, Roster, roster_id)
    ops = [op.model_dump(mode="json") for op in body.ops]
    result = svc.apply_changes(db, roster, ops, body.dry_run, body.override_reason)
    if result["committed"]:
        db.refresh(roster)
        result["roster"] = svc.roster_detail(db, roster)
    return result


@router.post("/rosters/{roster_id}/publish")
def publish(roster_id: int, body: PublishIn, db: Session = Depends(get_db)):
    roster = get_or_404(db, Roster, roster_id)
    validation = svc.publish(db, roster, body.override_reason)
    return {**svc.roster_summary(roster), "validation": validation}


@router.post("/rosters/{roster_id}/clone", status_code=201)
def clone(roster_id: int, db: Session = Depends(get_db)):
    return svc.roster_summary(svc.clone(db, get_or_404(db, Roster, roster_id)))


@router.post("/rosters/{roster_id}/regenerate", status_code=202)
def regenerate(roster_id: int, body: RegenerateIn, request: Request, db: Session = Depends(get_db)):
    roster = get_or_404(db, Roster, roster_id)
    if roster.status == "historical":
        raise HTTPException(status_code=409, detail="Historical rosters cannot be regenerated")
    req = RunRequest(
        year=roster.year, month=roster.month, project_ids=list(roster.project_ids or []),
        analyst_ids=list(roster.analyst_ids or []) or None,
        policy_id=(roster.policy_snapshot or {}).get("policy_id"),
        policy_overrides={k: v for k, v in (roster.policy_snapshot or {}).items()
                          if k not in ("policy_id", "policy_name", "solver_time_limit_seconds")},
        time_limit_seconds=body.time_limit_seconds, base_roster_id=roster.id,
        window_start=body.window_start, window_end=body.window_end,
        pending_leave_ids=body.simulate_pending_leave_ids,
    )
    st = request.app.state
    kind = "simulate" if body.simulate else "regenerate"
    run = svc.start_run(db, st.jobs, st.session_factory, req, kind, st.settings.max_solver_seconds)
    return {"run_id": run.id, "state": run.state}


@router.get("/jobs")
def list_jobs(limit: int = 20, request: Request = None, db: Session = Depends(get_db)):
    runs = db.scalars(select(SolverRun).order_by(SolverRun.created_at.desc()).limit(max(1, min(limit, 100))))
    return [svc.job_view(r, request.app.state.jobs) for r in runs]


@router.get("/jobs/{run_id}")
def get_job(run_id: str, request: Request, db: Session = Depends(get_db)):
    run = db.get(SolverRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return svc.job_view(run, request.app.state.jobs)


@router.post("/jobs/{run_id}/cancel")
def cancel_job(run_id: str, request: Request, db: Session = Depends(get_db)):
    run = db.get(SolverRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.state not in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"Run is already {run.state}")
    request.app.state.jobs.cancel(run_id)
    return {"run_id": run_id, "cancel_requested": True}
