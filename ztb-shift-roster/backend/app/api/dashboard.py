"""Dashboard aggregates for one month."""

from __future__ import annotations

from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Analyst, LeaveRequest, Project, Roster, SolverRun
from ..services import roster_service as svc
from ..services.problem_builder import month_bounds
from .deps import get_db

router = APIRouter(tags=["dashboard"])


def _current_rosters(db: Session, year: int, month: int) -> list[Roster]:
    published = list(db.scalars(select(Roster).where(Roster.year == year, Roster.month == month,
                                                     Roster.status == "published")))
    if published:
        return published
    latest = db.scalar(select(Roster).where(Roster.year == year, Roster.month == month, Roster.status == "draft")
                       .order_by(Roster.version.desc()))
    return [latest] if latest else []


@router.get("/dashboard")
def dashboard(request: Request, year: int | None = None, month: int | None = None, db: Session = Depends(get_db)):
    today = date.today()
    year, month = year or today.year, month or today.month
    start, end = month_bounds(year, month)
    active_projects = db.scalar(select(func.count(Project.id)).where(Project.active)) or 0
    active_analysts = db.scalar(select(func.count(Analyst.id)).where(Analyst.active)) or 0
    pending = list(db.scalars(select(LeaveRequest).where(LeaveRequest.status == "pending")
                              .order_by(LeaveRequest.start_date)))
    approved_in_month = db.scalar(select(func.count(LeaveRequest.id)).where(
        LeaveRequest.status == "approved", LeaveRequest.start_date <= end, LeaveRequest.end_date >= start)) or 0

    rosters = []
    distribution: Counter = Counter()
    workload: dict[int, dict] = {}
    alerts: list[dict] = []
    filled = total = 0
    for r in _current_rosters(db, year, month):
        inst, report = svc.validate_stored(db, r)
        data = report.to_dict()
        rosters.append({**svc.roster_summary(r), "is_valid": data["is_valid"], "error_count": data["error_count"],
                        "coverage_percent": data["coverage_percent"]})
        for c in report.coverage:
            total += 1
            filled += c["assigned"] >= c["required"]
        for a in r.assignments:
            sh = inst.shifts.get(a.shift_template_id)
            proj = inst.projects.get(a.project_id)
            distribution[(proj.code if proj else str(a.project_id), sh.code if sh else "?")] += 1
        for aid, m in report.metrics.items():
            w = workload.setdefault(aid, {"analyst_id": aid, "employee_code": inst.analysts[aid].code
                                          if aid in inst.analysts else str(aid),
                                          "shifts": 0, "hours": 0.0, "nights": 0, "weekend_shifts": 0, "leave_days": 0})
            for k in ("shifts", "hours", "nights", "weekend_shifts"):
                w[k] += m[k]
            w["leave_days"] = max(w["leave_days"], m["leave_days"])
        for v in report.errors:
            if v.rule in ("coverage", "absence", "overlap", "min_rest"):
                alerts.append({"roster_id": r.id, **v.to_dict()})
    names = {a.id: a.full_name for a in db.scalars(select(Analyst).where(Analyst.id.in_(list(workload))))}
    for aid, w in workload.items():
        w["full_name"] = names.get(aid, "")
    runs = db.scalars(select(SolverRun).order_by(SolverRun.created_at.desc()).limit(5))
    return {
        "year": year, "month": month,
        "totals": {"projects": active_projects, "active_analysts": active_analysts, "pending_leaves": len(pending),
                   "approved_leaves_this_month": approved_in_month},
        "coverage_percent": round(100.0 * filled / total, 1) if total else None,
        "rosters": rosters,
        "alerts": alerts[:50],
        "alert_count": len(alerts),
        "shift_distribution": [{"project": p, "shift": s, "count": n} for (p, s), n in sorted(distribution.items())],
        "workload": sorted(workload.values(), key=lambda w: w["employee_code"]),
        "pending_leaves": [{"id": lv.id, "analyst_id": lv.analyst_id, "start_date": lv.start_date.isoformat(),
                            "end_date": lv.end_date.isoformat(), "leave_type": lv.leave_type} for lv in pending[:10]],
        "recent_runs": [svc.job_view(r, request.app.state.jobs) | {"result": {}} for r in runs],
    }
