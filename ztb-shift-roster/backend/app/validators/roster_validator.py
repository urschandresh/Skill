"""Independent roster validator.

Re-checks every hard rule for a set of assignments without importing anything from
``app.solver``. Time handling uses timezone-aware ``datetime`` objects and run-length
counting, a different method from the solver's epoch-minute windows, so a bug in one is
unlikely to be repeated in the other. Rule semantics are documented in ``app/domain.py``.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from ..domain import Absence, ProblemInstance, ShiftDef, Slot

ERROR = "error"
WARNING = "warning"


@dataclass
class Violation:
    rule: str
    severity: str
    message: str
    analyst_id: int | None = None
    project_id: int | None = None
    shift_id: int | None = None
    date: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ValidationReport:
    violations: list[Violation] = field(default_factory=list)
    metrics: dict[int, dict] = field(default_factory=dict)
    coverage: list[dict] = field(default_factory=list)

    @property
    def errors(self) -> list[Violation]:
        return [v for v in self.violations if v.severity == ERROR]

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        counts = Counter(v.rule for v in self.violations)
        filled = sum(1 for c in self.coverage if c["assigned"] >= c["required"])
        return {
            "is_valid": self.is_valid,
            "error_count": len(self.errors),
            "warning_count": len(self.violations) - len(self.errors),
            "by_rule": dict(counts),
            "violations": [v.to_dict() for v in self.violations],
            "metrics": {str(k): v for k, v in self.metrics.items()},
            "coverage_percent": round(100.0 * filled / len(self.coverage), 1) if self.coverage else 100.0,
        }


def _local(d: date, hhmm: str, tz: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=ZoneInfo(tz))


def _span(shift: ShiftDef, d: date) -> tuple[datetime, datetime]:
    start = _local(d, shift.start_time, shift.timezone)
    end_date = d if shift.end_time > shift.start_time else d + timedelta(days=1)
    end = _local(end_date, shift.end_time, shift.timezone)
    return start, end


class _Absences:
    def __init__(self, absences: list[Absence]):
        self.full: dict[tuple[int, date], list[Absence]] = defaultdict(list)
        self.partial: dict[int, list[Absence]] = defaultdict(list)
        for ab in absences:
            (self.partial[ab.analyst_id] if ab.is_partial else self.full[(ab.analyst_id, ab.date)]).append(ab)

    def conflicts(self, analyst_id: int, shift: ShiftDef, d: date) -> Absence | None:
        for ab in self.full.get((analyst_id, d), []):
            if ab.kind == "block_shifts":
                if shift.code in ab.blocked_codes:
                    return ab
                continue
            if ab.project_id in (None, shift.project_id):
                return ab
        start, end = _span(shift, d)
        for ab in self.partial.get(analyst_id, []):
            ls, le = _local(ab.date, ab.start_time, ab.timezone), _local(ab.date, ab.end_time, ab.timezone)
            if start < le and ls < end:
                return ab
        return None

    def leave_day(self, analyst_id: int, d: date) -> bool:
        return any(
            ab.kind in ("leave", "holiday") and ab.project_id is None for ab in self.full.get((analyst_id, d), [])
        )

    def unavailable_day(self, analyst_id: int, d: date) -> bool:
        return any(
            ab.kind in ("leave", "holiday", "unavailable") and ab.project_id is None
            for ab in self.full.get((analyst_id, d), [])
        )


def validate_roster(inst: ProblemInstance, assignments: list[Slot], check_locks: bool = True) -> ValidationReport:
    report = ValidationReport()
    add = report.violations.append
    pol = inst.policy
    absences = _Absences(inst.absences)
    first, last = inst.start_date, inst.end_date

    def label(analyst_id: int) -> str:
        a = inst.analysts.get(analyst_id)
        return a.code if a else f"#{analyst_id}"

    def shift_label(slot: Slot) -> str:
        sh = inst.shifts.get(slot.shift_id)
        pr = inst.projects.get(slot.project_id)
        return f"{pr.code if pr else slot.project_id}/{sh.code if sh else slot.shift_id}"

    # ---- references, duplicates, eligibility, absences
    seen: set[Slot] = set()
    good: list[Slot] = []
    for slot in assignments:
        where = dict(analyst_id=slot.analyst_id, project_id=slot.project_id, shift_id=slot.shift_id,
                     date=slot.date.isoformat())
        if slot in seen:
            add(Violation("duplicate", ERROR, f"{label(slot.analyst_id)} assigned twice to {shift_label(slot)} on {slot.date}", **where))
            continue
        seen.add(slot)
        analyst = inst.analysts.get(slot.analyst_id)
        shift = inst.shifts.get(slot.shift_id)
        if analyst is None or shift is None or shift.project_id != slot.project_id:
            add(Violation("reference", ERROR, "Assignment refers to an unknown analyst, project or shift", **where))
            continue
        if not first <= slot.date <= last:
            add(Violation("outside_period", ERROR, f"Assignment on {slot.date} is outside the roster period", **where))
            continue
        if not shift.active:
            add(Violation("eligibility", ERROR, f"Shift {shift_label(slot)} is inactive", **where))
        allowed = analyst.eligibility.get(slot.project_id)
        project = inst.projects.get(slot.project_id)
        if allowed is None:
            add(Violation("eligibility", ERROR, f"{label(slot.analyst_id)} is not eligible for project {shift_label(slot).split('/')[0]}", **where))
        elif allowed and shift.code not in allowed:
            add(Violation("eligibility", ERROR, f"{label(slot.analyst_id)} may not work {shift_label(slot)}", **where))
        missing = (set(shift.required_skill_ids) | set(project.required_skill_ids if project else ())) - set(analyst.skill_ids)
        if missing:
            add(Violation("skills", ERROR, f"{label(slot.analyst_id)} lacks required skills for {shift_label(slot)}", **where))
        ab = absences.conflicts(slot.analyst_id, shift, slot.date)
        if ab is not None:
            what = {"leave": "approved leave", "holiday": "a work-blocking holiday",
                    "unavailable": "an availability exception", "block_shifts": "a blocked shift"}.get(ab.kind, ab.kind)
            add(Violation("absence", ERROR, f"{label(slot.analyst_id)} works {shift_label(slot)} on {slot.date} during {what}", **where))
        good.append(slot)

    # ---- per-analyst timeline (roster + fixed outside assignments)
    fixed = [f for f in inst.fixed if f.analyst_id in inst.analysts and f.shift_id in inst.shifts]
    timeline: dict[int, list[tuple[datetime, datetime, Slot, bool]]] = defaultdict(list)
    for slot in good:
        s, e = _span(inst.shifts[slot.shift_id], slot.date)
        timeline[slot.analyst_id].append((s, e, slot, False))
    for slot in fixed:
        s, e = _span(inst.shifts[slot.shift_id], slot.date)
        timeline[slot.analyst_id].append((s, e, slot, True))

    rest = timedelta(hours=pol.min_rest_hours)
    for analyst_id, items in timeline.items():
        items.sort(key=lambda t: t[0])
        for i, (s1, e1, slot1, fixed1) in enumerate(items):
            for s2, e2, slot2, fixed2 in items[i + 1 :]:
                if s2 >= e1 + rest:
                    break
                if fixed1 and fixed2:
                    continue
                target = slot2 if not fixed2 else slot1
                where = dict(analyst_id=analyst_id, project_id=target.project_id, shift_id=target.shift_id,
                             date=target.date.isoformat())
                if s2 < e1 and s1 < e2:
                    add(Violation("overlap", ERROR, f"{label(analyst_id)} has overlapping shifts {shift_label(slot1)} "
                                  f"({slot1.date}) and {shift_label(slot2)} ({slot2.date})", **where))
                else:
                    gap_h = (s2 - e1).total_seconds() / 3600
                    add(Violation("min_rest", ERROR, f"{label(analyst_id)} gets only {gap_h:.1f}h rest between "
                                  f"{shift_label(slot1)} ({slot1.date}) and {shift_label(slot2)} ({slot2.date}); "
                                  f"minimum is {pol.min_rest_hours}h", **where))

    # ---- day maps
    worked_days: dict[int, Counter] = defaultdict(Counter)
    night_days: dict[int, set[date]] = defaultdict(set)
    minutes_by_day: dict[int, Counter] = defaultdict(Counter)
    for analyst_id, items in timeline.items():
        for s, e, slot, _f in items:
            worked_days[analyst_id][slot.date] += 1
            minutes_by_day[analyst_id][slot.date] += int((e - s).total_seconds() // 60)
            if inst.shifts[slot.shift_id].is_night:
                night_days[analyst_id].add(slot.date)

    if pol.one_shift_per_day:
        for analyst_id, days in worked_days.items():
            for d, n in days.items():
                if n > 1 and first <= d <= last:
                    add(Violation("one_shift_per_day", ERROR, f"{label(analyst_id)} has {n} shifts on {d}",
                                  analyst_id=analyst_id, date=d.isoformat()))

    def known(analyst_id: int, d: date) -> bool:
        since = inst.history_known_from.get(analyst_id)
        return first <= d <= last or (since is not None and since <= d < first)

    # ---- weekly days and hours
    ws = first - timedelta(days=(first.weekday() - pol.week_start_day) % 7)
    while ws <= last:
        days = [ws + timedelta(days=i) for i in range(7)]
        for analyst_id, analyst in inst.analysts.items():
            leave = sum(absences.leave_day(analyst_id, d) for d in days)
            unavailable = sum(absences.unavailable_day(analyst_id, d) for d in days)
            unknown_free = sum(1 for d in days if not known(analyst_id, d) and not absences.unavailable_day(analyst_id, d))
            n = pol.working_days_per_week
            upper = max(0, n - leave) if pol.leave_counts_as_working_day else min(n, 7 - leave)
            lower = max(0, min(upper, 7 - unavailable) - unknown_free) if pol.weekly_mode == "exact" else 0
            worked = sum(1 for d in days if known(analyst_id, d) and worked_days[analyst_id][d] > 0)
            where = dict(analyst_id=analyst_id, date=ws.isoformat())
            before = sum(1 for d in days if d < first and known(analyst_id, d) and worked_days[analyst_id][d] > 0)
            if before:
                in_period = [d for d in days if first <= d <= last]
                fixed_dates = {f.date for f in fixed if f.analyst_id == analyst_id}
                reachable = before + sum(
                    1 for d in in_period if d in fixed_dates or not absences.unavailable_day(analyst_id, d))
                if lower > reachable or upper < before:
                    add(Violation("weekly_days_inherited", WARNING,
                                  f"{label(analyst_id)}: week of {ws} straddles the roster start and the previous "
                                  f"roster already makes the {n}-day rule unreachable; checked against what this "
                                  f"roster can still change", **where))
                lower = min(lower, reachable)
                upper = max(upper, before)
            if worked > upper:
                add(Violation("weekly_days", ERROR, f"{label(analyst_id)} works {worked} days in week of {ws}; "
                              f"maximum is {upper}", **where))
            elif worked < lower:
                add(Violation("weekly_days", ERROR, f"{label(analyst_id)} works {worked} days in week of {ws}; "
                              f"policy requires {lower}", **where))
            limit_h = analyst.max_hours_per_week or pol.max_hours_per_week
            minutes = sum(minutes_by_day[analyst_id][d] for d in days)
            if minutes > limit_h * 60:
                add(Violation("weekly_hours", ERROR, f"{label(analyst_id)} works {minutes / 60:.1f}h in week of {ws}; "
                              f"maximum is {limit_h}h", **where))
        ws += timedelta(days=7)

    # ---- consecutive runs (unknown days break a run)
    def runs(analyst_id: int, is_on) -> list[tuple[date, int]]:
        out, start, length = [], None, 0
        d = first - timedelta(days=31)
        while d <= last:
            if known(analyst_id, d) and is_on(d):
                if length == 0:
                    start = d
                length += 1
            else:
                if length:
                    out.append((start, length))
                length = 0
            d += timedelta(days=1)
        if length:
            out.append((start, length))
        return out

    for analyst_id in inst.analysts:
        for start, length in runs(analyst_id, lambda d, a=analyst_id: worked_days[a][d] > 0):
            if length > pol.max_consecutive_work_days and start + timedelta(days=length - 1) >= first:
                add(Violation("consecutive_days", ERROR, f"{label(analyst_id)} works {length} consecutive days from "
                              f"{start}; maximum is {pol.max_consecutive_work_days}",
                              analyst_id=analyst_id, date=start.isoformat()))
        for start, length in runs(analyst_id, lambda d, a=analyst_id: d in night_days[a]):
            if length > pol.max_consecutive_nights and start + timedelta(days=length - 1) >= first:
                add(Violation("consecutive_nights", ERROR, f"{label(analyst_id)} works {length} consecutive nights "
                              f"from {start}; maximum is {pol.max_consecutive_nights}",
                              analyst_id=analyst_id, date=start.isoformat()))

    # ---- coverage
    count = Counter((s.project_id, s.shift_id, s.date) for s in good)
    count.update((s.project_id, s.shift_id, s.date) for s in fixed if first <= s.date <= last)
    for (p, s, d), (mn, mx) in sorted(inst.requirements.items(), key=lambda kv: (kv[0][2], kv[0][0], kv[0][1])):
        got = count.get((p, s, d), 0)
        report.coverage.append({"project_id": p, "shift_id": s, "date": d.isoformat(), "required": mn,
                                "max": mx, "assigned": got})
        tag = f"{inst.projects[p].code if p in inst.projects else p}/{inst.shifts[s].code if s in inst.shifts else s}"
        if got < mn:
            add(Violation("coverage", ERROR, f"{tag} on {d} has {got} of {mn} required analysts",
                          project_id=p, shift_id=s, date=d.isoformat()))
        if mx is not None and got > mx:
            add(Violation("coverage_max", ERROR, f"{tag} on {d} has {got} analysts; maximum is {mx}",
                          project_id=p, shift_id=s, date=d.isoformat()))

    # ---- locks
    if check_locks:
        present = set(good)
        for slot in inst.locked:
            if slot not in present:
                add(Violation("locked", ERROR, f"Locked assignment {label(slot.analyst_id)} {shift_label(slot)} on "
                              f"{slot.date} is missing", analyst_id=slot.analyst_id, project_id=slot.project_id,
                              shift_id=slot.shift_id, date=slot.date.isoformat()))

    # ---- metrics
    for analyst_id in inst.analysts:
        mine = [s for s in good if s.analyst_id == analyst_id]
        report.metrics[analyst_id] = {
            "shifts": len(mine),
            "worked_days": len({s.date for s in mine}),
            "nights": sum(1 for s in mine if inst.shifts[s.shift_id].is_night),
            "weekend_shifts": sum(1 for s in mine if s.date.weekday() >= 5),
            "hours": round(sum(minutes_by_day[analyst_id][d] for d in {s.date for s in mine}) / 60, 1),
            "leave_days": sum(1 for i in range((last - first).days + 1)
                              if absences.leave_day(analyst_id, first + timedelta(days=i))),
            "by_code": dict(Counter(inst.shifts[s.shift_id].code for s in mine)),
        }
    return report
