"""Leave requests: submit, edit, decide, cancel, assess impact, suggest cover, regenerate."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Analyst, LeaveRequest, Roster
from ..schemas.common import StrictModel
from ..schemas.scheduling import LeaveDecision, LeaveIn, LeaveOut
from ..services import leave_service, roster_service
from ..services.audit import record
from ..services.problem_builder import RunRequest
from .deps import get_db, get_or_404

router = APIRouter(tags=["leave"])


class LeaveRegenerateIn(StrictModel):
    roster_id: int
    margin_days: int = Field(default=2, ge=0, le=31)
    time_limit_seconds: int | None = Field(default=None, ge=1, le=600)
    simulate: bool = False


@router.get("/leaves", response_model=list[LeaveOut])
def list_leaves(status: str | None = None, analyst_id: int | None = None, start: date | None = None,
                end: date | None = None, db: Session = Depends(get_db)):
    q = select(LeaveRequest).order_by(LeaveRequest.start_date.desc())
    if status:
        q = q.where(LeaveRequest.status == status)
    if analyst_id is not None:
        q = q.where(LeaveRequest.analyst_id == analyst_id)
    if start is not None:
        q = q.where(LeaveRequest.end_date >= start)
    if end is not None:
        q = q.where(LeaveRequest.start_date <= end)
    return list(db.scalars(q))


@router.get("/leaves/{leave_id}", response_model=LeaveOut)
def get_leave(leave_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, LeaveRequest, leave_id, "Leave")


@router.post("/leaves", response_model=LeaveOut, status_code=201)
def submit_leave(body: LeaveIn, db: Session = Depends(get_db)):
    get_or_404(db, Analyst, body.analyst_id)
    overlap = db.scalar(select(LeaveRequest).where(
        LeaveRequest.analyst_id == body.analyst_id, LeaveRequest.status.in_(("pending", "approved")),
        LeaveRequest.start_date <= body.end_date, LeaveRequest.end_date >= body.start_date,
        LeaveRequest.partial_day.is_(False)))
    if overlap is not None and not body.partial_day:
        raise HTTPException(status_code=409, detail=f"Overlaps existing leave #{overlap.id}")
    leave = LeaveRequest(**body.model_dump(), status="pending")
    db.add(leave)
    db.flush()
    record(db, "submit", "leave", leave.id)
    db.commit()
    return leave


@router.put("/leaves/{leave_id}", response_model=LeaveOut)
def edit_leave(leave_id: int, body: LeaveIn, db: Session = Depends(get_db)):
    leave = get_or_404(db, LeaveRequest, leave_id, "Leave")
    if leave.status not in ("pending", "approved"):
        raise HTTPException(status_code=409, detail=f"A {leave.status} leave cannot be edited")
    if body.analyst_id != leave.analyst_id:
        raise HTTPException(status_code=422, detail="Leave cannot be moved to another analyst")
    for k, v in body.model_dump().items():
        setattr(leave, k, v)
    if leave.status == "approved":
        leave.status = "pending"  # changed dates need a fresh decision
        leave.decision_note = "Edited after approval; awaiting re-approval"
    record(db, "edit", "leave", leave.id)
    db.commit()
    return leave


@router.post("/leaves/{leave_id}/approve", response_model=LeaveOut)
def approve(leave_id: int, body: LeaveDecision, db: Session = Depends(get_db)):
    return leave_service.transition(db, get_or_404(db, LeaveRequest, leave_id, "Leave"), "approve", body.note)


@router.post("/leaves/{leave_id}/reject", response_model=LeaveOut)
def reject(leave_id: int, body: LeaveDecision, db: Session = Depends(get_db)):
    return leave_service.transition(db, get_or_404(db, LeaveRequest, leave_id, "Leave"), "reject", body.note)


@router.post("/leaves/{leave_id}/cancel", response_model=LeaveOut)
def cancel(leave_id: int, body: LeaveDecision, db: Session = Depends(get_db)):
    return leave_service.transition(db, get_or_404(db, LeaveRequest, leave_id, "Leave"), "cancel", body.note)


@router.get("/leaves/{leave_id}/impact")
def impact(leave_id: int, roster_id: int | None = None, db: Session = Depends(get_db)):
    return leave_service.impact(db, get_or_404(db, LeaveRequest, leave_id, "Leave"), roster_id)


@router.get("/leaves/{leave_id}/replacements")
def replacements(leave_id: int, roster_id: int | None = None, db: Session = Depends(get_db)):
    return leave_service.replacements(db, get_or_404(db, LeaveRequest, leave_id, "Leave"), roster_id)


@router.post("/leaves/{leave_id}/regenerate", status_code=202)
def regenerate_for_leave(leave_id: int, body: LeaveRegenerateIn, request: Request, db: Session = Depends(get_db)):
    """Re-solve only the days around the leave; everything else in the roster is locked.

    With ``simulate`` the leave is treated as approved but nothing is saved: the job result
    lists how many assignments would change. Without it the leave must already be approved
    and a new draft version is created.
    """
    leave = get_or_404(db, LeaveRequest, leave_id, "Leave")
    roster = get_or_404(db, Roster, body.roster_id)
    if roster.status == "historical":
        raise HTTPException(status_code=409, detail="Historical rosters cannot be regenerated")
    if not body.simulate and leave.status != "approved":
        raise HTTPException(status_code=409, detail="Approve the leave first, or run a simulation")
    lo, hi = leave_service.regeneration_window(leave, roster, body.margin_days)
    snapshot = roster.policy_snapshot or {}
    req = RunRequest(
        year=roster.year, month=roster.month, project_ids=list(roster.project_ids or []),
        analyst_ids=list(roster.analyst_ids or []) or None, policy_id=snapshot.get("policy_id"),
        policy_overrides={k: v for k, v in snapshot.items()
                          if k not in ("policy_id", "policy_name", "solver_time_limit_seconds")},
        time_limit_seconds=body.time_limit_seconds, base_roster_id=roster.id, window_start=lo, window_end=hi,
        pending_leave_ids=[leave.id] if body.simulate else [],
    )
    st = request.app.state
    run = roster_service.start_run(db, st.jobs, st.session_factory, req,
                                   "simulate" if body.simulate else "regenerate", st.settings.max_solver_seconds)
    return {"run_id": run.id, "state": run.state, "window_start": lo.isoformat(), "window_end": hi.isoformat()}
