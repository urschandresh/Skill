"""SYNTHETIC demo data. Every name, code and date here is invented and labelled as such."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Analyst, AnalystProject, LeaveRequest, Project, ShiftTemplate, Skill, StaffingRequirement
from .audit import record
from .seed import DEFAULT_SHIFT_TEMPLATES

FIRST = ["Aarav", "Diya", "Kabir", "Meera", "Rohan", "Sana", "Vikram", "Isha", "Arjun", "Nisha", "Dev", "Tara"]


def load_demo_data(session: Session, today: date | None = None) -> dict:
    if (session.scalar(select(func.count(Project.id))) or 0) or (session.scalar(select(func.count(Analyst.id))) or 0):
        raise HTTPException(status_code=409, detail="Demo data can only be loaded into an empty database")
    today = today or date.today()
    siem = Skill(name="SIEM", description="Synthetic skill")
    edr = Skill(name="EDR", description="Synthetic skill")
    session.add_all([siem, edr])
    session.flush()

    projects = []
    for code, name, n_staff in (("SYN-A", "Synthetic SOC Alpha", 1), ("SYN-B", "Synthetic SOC Beta", 1)):
        p = Project(code=code, name=name, description="SYNTHETIC demo project", timezone="Asia/Kolkata")
        session.add(p)
        session.flush()
        for tpl in DEFAULT_SHIFT_TEMPLATES:
            t = ShiftTemplate(project_id=p.id, **tpl)
            session.add(t)
            session.flush()
            session.add(StaffingRequirement(project_id=p.id, shift_template_id=t.id, min_staff=n_staff))
        projects.append(p)
    alpha, beta = projects
    # Alpha needs two analysts on weekday mornings.
    session.flush()
    session.refresh(alpha)
    morning = next(t for t in alpha.shift_templates if t.code == "M")
    for wd in range(5):
        session.add(StaffingRequirement(project_id=alpha.id, shift_template_id=morning.id, weekday=wd, min_staff=2))

    analysts = []
    for i, first in enumerate(FIRST):
        a = Analyst(employee_code=f"SYN-{i + 1:03d}", full_name=f"{first} Synthetic", active=True,
                    notes="SYNTHETIC demo analyst", skills=[siem] if i % 3 else [siem, edr],
                    preferences={"preferred_shifts": ["M"]} if i == 2 else ({"avoid_shifts": ["N"]} if i == 5 else {}))
        session.add(a)
        session.flush()
        if i < 7:
            session.add(AnalystProject(analyst_id=a.id, project_id=alpha.id, is_primary=True))
            if i in (5, 6):
                session.add(AnalystProject(analyst_id=a.id, project_id=beta.id))
        else:
            session.add(AnalystProject(analyst_id=a.id, project_id=beta.id, is_primary=True))
        analysts.append(a)

    nxt = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    session.add(LeaveRequest(analyst_id=analysts[1].id, start_date=nxt + timedelta(days=9),
                             end_date=nxt + timedelta(days=11), leave_type="annual", status="approved",
                             reason="SYNTHETIC approved leave"))
    session.add(LeaveRequest(analyst_id=analysts[3].id, start_date=nxt + timedelta(days=17),
                             end_date=nxt + timedelta(days=17), leave_type="casual", status="pending",
                             reason="SYNTHETIC pending leave"))
    session.add(LeaveRequest(analyst_id=analysts[8].id, start_date=nxt + timedelta(days=4),
                             end_date=nxt + timedelta(days=4), leave_type="sick", partial_day=True,
                             start_time="09:00", end_time="13:00", status="approved", reason="SYNTHETIC partial"))
    record(session, "load_demo", "system", "", analysts=len(analysts), projects=len(projects))
    session.commit()
    return {"projects": len(projects), "analysts": len(analysts), "leaves": 3, "month_with_leave": nxt.isoformat()}
