"""SYNTHETIC test fixtures. Every analyst, project and assignment here is invented."""

from __future__ import annotations

from datetime import date, timedelta

from app.domain import AnalystDef, Policy, ProblemInstance, ProjectDef, ShiftDef

TZ = "Asia/Kolkata"


def shifts_for(project_id: int, base_id: int) -> dict[int, ShiftDef]:
    return {
        base_id: ShiftDef(base_id, project_id, "M", "06:00", "15:00", False, TZ),
        base_id + 1: ShiftDef(base_id + 1, project_id, "A", "14:00", "23:00", False, TZ),
        base_id + 2: ShiftDef(base_id + 2, project_id, "N", "22:00", "07:00", True, TZ),
    }


def make_instance(
    n_analysts: int = 7,
    year: int = 2026,
    month: int = 11,
    days: int | None = None,
    n_projects: int = 1,
    min_staff: int = 1,
    policy: Policy | None = None,
    shared_analysts: bool = False,
) -> ProblemInstance:
    start = date(year, month, 1)
    nxt = date(year + (month == 12), month % 12 + 1, 1)
    end = nxt - timedelta(days=1) if days is None else start + timedelta(days=days - 1)
    projects, shifts = {}, {}
    for i in range(n_projects):
        pid = i + 1
        projects[pid] = ProjectDef(pid, f"SYN{pid}", TZ)
        shifts.update(shifts_for(pid, pid * 10))
    analysts = {}
    for i in range(n_analysts):
        aid = 100 + i
        if shared_analysts or n_projects == 1:
            elig = {pid: frozenset() for pid in projects}
        else:
            elig = {(i % n_projects) + 1: frozenset()}
        analysts[aid] = AnalystDef(aid, f"SYN-{i + 1:03d}", frozenset(), elig)
    reqs = {}
    d = start
    while d <= end:
        for sh in shifts.values():
            reqs[(sh.project_id, sh.id, d)] = (min_staff, None)
        d += timedelta(days=1)
    return ProblemInstance(start, end, projects, shifts, analysts, reqs, policy=policy or Policy())
