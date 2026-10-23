"""Which (analyst, project, shift, date) slots may be used at all, and why others may not."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from ..domain import Absence, AnalystDef, ProblemInstance, ShiftDef, Slot


@lru_cache(maxsize=64)
def _zone(name: str) -> ZoneInfo:
    return ZoneInfo(name)


def _epoch_minutes(d: date, hhmm: str, tz: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    local = datetime(d.year, d.month, d.day, h, m, tzinfo=_zone(tz))
    return int(local.timestamp()) // 60


def shift_interval(shift: ShiftDef, d: date) -> tuple[int, int]:
    """Absolute [start, end) in minutes since the Unix epoch."""
    start = _epoch_minutes(d, shift.start_time, shift.timezone)
    end_day = d + timedelta(days=1) if shift.end_time <= shift.start_time else d
    end = _epoch_minutes(end_day, shift.end_time, shift.timezone)
    return start, end


def shift_minutes(shift: ShiftDef, d: date) -> int:
    s, e = shift_interval(shift, d)
    return e - s


def eligibility_reason(inst: ProblemInstance, a: AnalystDef, shift: ShiftDef) -> str | None:
    """None when the analyst may work this shift; otherwise a short reason."""
    if not shift.active:
        return "shift template inactive"
    allowed = a.eligibility.get(shift.project_id)
    if allowed is None:
        return "not eligible for project"
    if allowed and shift.code not in allowed:
        return f"shift {shift.code} not allowed for analyst on this project"
    project = inst.projects.get(shift.project_id)
    needed = set(shift.required_skill_ids) | (set(project.required_skill_ids) if project else set())
    if not needed <= set(a.skill_ids):
        return "missing required skill"
    return None


@dataclass
class AbsenceIndex:
    by_day: dict[tuple[int, date], list[Absence]]
    partial: dict[int, list[tuple[int, int, Absence]]]

    @classmethod
    def build(cls, absences: list[Absence]) -> AbsenceIndex:
        by_day: dict[tuple[int, date], list[Absence]] = defaultdict(list)
        partial: dict[int, list[tuple[int, int, Absence]]] = defaultdict(list)
        for ab in absences:
            if ab.is_partial:
                s = _epoch_minutes(ab.date, ab.start_time, ab.timezone)
                e = _epoch_minutes(ab.date, ab.end_time, ab.timezone)
                partial[ab.analyst_id].append((s, e, ab))
            else:
                by_day[(ab.analyst_id, ab.date)].append(ab)
        return cls(by_day, partial)

    def blocking(self, analyst_id: int, shift: ShiftDef, d: date) -> Absence | None:
        for ab in self.by_day.get((analyst_id, d), ()):
            if ab.kind == "block_shifts":
                if shift.code in ab.blocked_codes:
                    return ab
            elif ab.project_id is None or ab.project_id == shift.project_id:
                return ab
        partial = self.partial.get(analyst_id)
        if partial:
            s, e = shift_interval(shift, d)
            for ps, pe, ab in partial:
                if ps < e and s < pe:
                    return ab
        return None

    def full_leave_days(self, analyst_id: int, d: date) -> bool:
        return any(ab.counts_as_leave_day for ab in self.by_day.get((analyst_id, d), ()))

    def fully_unavailable(self, analyst_id: int, d: date) -> bool:
        return any(
            ab.kind in ("leave", "holiday", "unavailable") and ab.project_id is None
            for ab in self.by_day.get((analyst_id, d), ())
        )


@dataclass
class Candidates:
    slots: list[Slot]
    # Slots ruled out only by an absence (the analyst is otherwise eligible).
    blocked: dict[Slot, Absence]
    ineligible_reasons: dict[tuple[int, int], str]  # (analyst_id, shift_id) -> reason
    absences: AbsenceIndex


def build_candidates(inst: ProblemInstance) -> Candidates:
    absences = AbsenceIndex.build(inst.absences)
    selected = inst.selected_project_ids()
    shifts = [s for s in inst.shifts.values() if s.project_id in selected]
    slots: list[Slot] = []
    blocked: dict[Slot, Absence] = {}
    reasons: dict[tuple[int, int], str] = {}
    dates = inst.dates()
    for a in inst.analysts.values():
        for sh in shifts:
            reason = eligibility_reason(inst, a, sh)
            if reason:
                reasons[(a.id, sh.id)] = reason
                continue
            for d in dates:
                if (sh.project_id, sh.id, d) not in inst.requirements:
                    continue
                slot = Slot(a.id, sh.project_id, sh.id, d)
                ab = absences.blocking(a.id, sh, d)
                if ab is not None:
                    blocked[slot] = ab
                else:
                    slots.append(slot)
    return Candidates(slots, blocked, reasons, absences)


def week_start(d: date, week_start_day: int) -> date:
    return d - timedelta(days=(d.weekday() - week_start_day) % 7)
