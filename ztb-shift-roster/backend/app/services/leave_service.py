"""Leave lifecycle, impact assessment and replacement suggestions."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import Slot
from ..models import LeaveRequest, Roster, utcnow
from ..validators.roster_validator import validate_roster
from .audit import record
from .problem_builder import instance_for_roster, month_bounds

TRANSITIONS = {
    "approve": ({"pending"}, "approved"),
    "reject": ({"pending"}, "rejected"),
    "cancel": ({"pending", "approved"}, "cancelled"),
}


def transition(session: Session, leave: LeaveRequest, action: str, note: str) -> LeaveRequest:
    allowed, target = TRANSITIONS[action]
    if leave.status not in allowed:
        raise HTTPException(status_code=409, detail=f"Cannot {action} a leave that is {leave.status}")
    leave.status = target
    leave.decision_note = note
    leave.decided_at = utcnow()
    record(session, action, "leave", leave.id)
    session.commit()
    return leave


def rosters_for_leave(session: Session, leave: LeaveRequest, roster_id: int | None) -> list[Roster]:
    if roster_id is not None:
        roster = session.get(Roster, roster_id)
        if roster is None:
            raise HTTPException(status_code=404, detail="Roster not found")
        return [roster]
    out = []
    y, m = leave.start_date.year, leave.start_date.month
    while (y, m) <= (leave.end_date.year, leave.end_date.month):
        published = list(session.scalars(select(Roster).where(Roster.year == y, Roster.month == m,
                                                              Roster.status == "published")))
        if not published:
            latest = session.scalar(select(Roster).where(Roster.year == y, Roster.month == m,
                                                         Roster.status == "draft").order_by(Roster.version.desc()))
            published = [latest] if latest else []
        out.extend(published)
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _key(v) -> tuple:
    return (v.rule, v.analyst_id, v.project_id, v.shift_id, v.date, v.message)


def impact(session: Session, leave: LeaveRequest, roster_id: int | None = None) -> dict:
    """What happens to the roster(s) if this leave is (or stays) granted."""
    results = []
    for roster in rosters_for_leave(session, leave, roster_id):
        without = instance_for_roster(session, roster, exclude_leave_ids=[leave.id])
        # Evaluate the leave as if approved, without changing anything stored.
        with_leave = instance_for_roster(session, roster, pending_leave_ids=[leave.id])
        slots = [Slot(a.analyst_id, a.project_id, a.shift_template_id, a.date) for a in roster.assignments]
        base_report = validate_roster(without, slots)
        leave_report = validate_roster(with_leave, slots)
        base_keys = {_key(v) for v in base_report.errors}
        affected = [a for a in roster.assignments if a.analyst_id == leave.analyst_id
                    and any(v.rule == "absence" and v.analyst_id == a.analyst_id and v.date == a.date.isoformat()
                            and v.shift_id == a.shift_template_id for v in leave_report.errors)]
        # If those shifts are removed, which hard rules break (coverage, weekly days, ...)?
        remaining = [s for s in slots if not any(
            (s.analyst_id, s.shift_id, s.date) == (a.analyst_id, a.shift_template_id, a.date) for a in affected)]
        removed_report = validate_roster(with_leave, remaining)
        results.append({
            "roster_id": roster.id, "roster_name": roster.name, "roster_status": roster.status,
            "affected_assignments": [{"id": a.id, "date": a.date.isoformat(), "project_id": a.project_id,
                                      "shift_template_id": a.shift_template_id, "locked": a.locked} for a in affected],
            "conflicts_if_kept": [v.to_dict() for v in leave_report.errors if _key(v) not in base_keys],
            "consequences_if_removed": [v.to_dict() for v in removed_report.errors
                                        if _key(v) not in base_keys and v.rule != "absence"],
        })
    return {
        "leave_id": leave.id, "status": leave.status,
        "evaluated_as": "approved (simulation; nothing is changed)" if leave.status == "pending" else leave.status,
        "rosters": results,
        "no_roster": not results,
    }


def replacements(session: Session, leave: LeaveRequest, roster_id: int | None = None, limit: int = 5) -> dict:
    """For each shift the leave takes away, rank analysts who could take it without breaking rules."""
    out = []
    for roster in rosters_for_leave(session, leave, roster_id):
        inst = instance_for_roster(session, roster, pending_leave_ids=[leave.id])
        current = [Slot(a.analyst_id, a.project_id, a.shift_template_id, a.date) for a in roster.assignments]
        affected = [s for s in current if s.analyst_id == leave.analyst_id
                    and leave.start_date - timedelta(days=1) <= s.date <= leave.end_date]
        base_without = [s for s in current if s not in affected]
        base_report = validate_roster(instance_for_roster(session, roster, exclude_leave_ids=[leave.id]),
                                      base_without)
        base_keys = {_key(v) for v in base_report.errors}
        hours = {a: m["hours"] for a, m in base_report.metrics.items()}
        nights = {a: m["nights"] for a, m in base_report.metrics.items()}
        for slot in affected:
            check = validate_roster(inst, [*base_without, slot])
            if not any(v.rule == "absence" and v.date == slot.date.isoformat() for v in check.errors):
                continue  # this shift is compatible with the leave (e.g. partial-day leave)
            candidates = []
            for aid in inst.analysts:
                if aid == leave.analyst_id:
                    continue
                trial = Slot(aid, slot.project_id, slot.shift_id, slot.date)
                if trial in base_without:
                    continue
                report = validate_roster(inst, [*base_without, trial])
                new = [v for v in report.errors if _key(v) not in base_keys]
                # Moving a shift onto someone can push them over weekly limits; we report it, not hide it.
                candidates.append({
                    "analyst_id": aid, "employee_code": inst.analysts[aid].code,
                    "new_violations": [v.to_dict() for v in new], "ok": not new,
                    "month_hours": hours.get(aid, 0), "month_nights": nights.get(aid, 0),
                })
            candidates.sort(key=lambda c: (not c["ok"], len(c["new_violations"]), c["month_hours"], c["month_nights"]))
            out.append({"roster_id": roster.id, "date": slot.date.isoformat(), "project_id": slot.project_id,
                        "shift_template_id": slot.shift_id, "candidates": candidates[:limit],
                        "fully_valid_options": sum(1 for c in candidates if c["ok"])})
    return {"leave_id": leave.id, "shifts": out,
            "note": "Candidates with ok=true can take the shift with no new rule violations. Others list exactly "
                    "which rules they would break; regenerating the affected window often finds a cleaner fix."}


def regeneration_window(leave: LeaveRequest, roster: Roster, margin_days: int) -> tuple[date, date]:
    start, end = month_bounds(roster.year, roster.month)
    lo = max(start, leave.start_date - timedelta(days=margin_days))
    hi = min(end, leave.end_date + timedelta(days=margin_days))
    if lo > hi:
        raise HTTPException(status_code=422, detail="The leave does not fall in this roster's month")
    return lo, hi
