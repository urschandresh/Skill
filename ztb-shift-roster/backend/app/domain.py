"""Plain-data description of one scheduling problem.

Both the CP-SAT solver and the independent validator consume a ``ProblemInstance``. It holds
IDs and numbers only (no names or contact details), so it can be logged or saved for
debugging without exposing staff information.

Shared rule semantics (the solver and validator implement these separately):

* A shift belongs to the date it STARTS on, in its project's timezone. An end time at or
  before the start time means the shift ends the next day.
* Full-day leave, ``unavailable`` exceptions and work-blocking holidays block shifts whose
  date falls on the absent day. Partial-day leave blocks any shift whose time overlaps the
  leave window.
* Two shifts for the same analyst conflict when they overlap or when the gap between the end
  of one and the start of the next is shorter than ``min_rest_hours``.
* Weeks start on ``week_start_day`` (0 = Monday). For each week, with N working days per
  week, L full leave days (plus work-blocking holidays) and U days whose roster is unknown
  (outside the horizon and not covered by history):
    upper = N - L                 if leave counts as a working day, else min(N, 7 - L)
    lower = max(0, min(upper, 7 - L - B) - U)   in "exact" mode (B = fully unavailable days)
    lower = 0                     in "max" mode
  and the worked days in that week must lie in [lower, upper].
  In a week that straddles the roster start, days already worked in the previous roster
  count, but the bounds are limited to what this roster can still change:
    lower <= history_worked + (horizon days in the week the analyst is available)
    upper >= history_worked
  When that limit applies, it is reported as an explicit "inherited" warning.
* Consecutive-day and consecutive-night limits are checked on every window of
  limit + 1 consecutive days whose roster is fully known.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass(frozen=True)
class ShiftDef:
    id: int
    project_id: int
    code: str
    start_time: str  # HH:MM local
    end_time: str  # HH:MM local; <= start_time means next day
    is_night: bool
    timezone: str
    required_skill_ids: frozenset[int] = frozenset()
    active: bool = True


@dataclass(frozen=True)
class ProjectDef:
    id: int
    code: str
    timezone: str
    required_skill_ids: frozenset[int] = frozenset()


@dataclass(frozen=True)
class AnalystDef:
    id: int
    code: str
    skill_ids: frozenset[int]
    # project_id -> allowed shift codes (empty frozenset = every shift of the project)
    eligibility: dict[int, frozenset[str]]
    max_hours_per_week: int | None = None
    preferred_shifts: frozenset[str] = frozenset()
    avoid_shifts: frozenset[str] = frozenset()
    preferred_off_days: frozenset[int] = frozenset()


@dataclass(frozen=True)
class Absence:
    """kind: leave | holiday | unavailable | block_shifts"""

    analyst_id: int
    date: date
    kind: str
    start_time: str | None = None  # partial-day leave window (local time)
    end_time: str | None = None
    timezone: str = "Asia/Kolkata"
    blocked_codes: frozenset[str] = frozenset()
    project_id: int | None = None  # holidays limited to one project
    leave_id: int | None = None

    @property
    def is_partial(self) -> bool:
        return self.start_time is not None and self.end_time is not None

    @property
    def counts_as_leave_day(self) -> bool:
        """Full-day leave and work-blocking holidays reduce the weekly working-day target."""
        return self.kind in ("leave", "holiday") and not self.is_partial and self.project_id is None


@dataclass(frozen=True, order=True)
class Slot:
    """One shift on one date for one analyst."""

    analyst_id: int
    project_id: int
    shift_id: int
    date: date


@dataclass
class Policy:
    working_days_per_week: int = 5
    week_start_day: int = 0
    weekly_mode: str = "exact"
    max_hours_per_week: int = 48
    max_consecutive_work_days: int = 6
    max_consecutive_nights: int = 5
    min_rest_hours: int = 11
    one_shift_per_day: bool = True
    leave_counts_as_working_day: bool = True
    solver_time_limit_seconds: int = 30
    weights: dict[str, int] = field(
        default_factory=lambda: {
            "fair_nights": 10,
            "fair_weekends": 8,
            "balanced_hours": 5,
            "preferences": 2,
            "shift_changes": 3,
            "disruption": 20,
        }
    )


@dataclass
class ProblemInstance:
    start_date: date
    end_date: date  # inclusive
    projects: dict[int, ProjectDef]
    shifts: dict[int, ShiftDef]
    analysts: dict[int, AnalystDef]
    # (project_id, shift_id, date) -> (min_staff, max_staff or None); only selected projects
    requirements: dict[tuple[int, int, date], tuple[int, int | None]]
    absences: list[Absence] = field(default_factory=list)
    locked: list[Slot] = field(default_factory=list)
    # Assignments outside this roster that are already fixed: the previous month's tail
    # and other published rosters in the same period. They count for rest, weekly and
    # consecutive rules but are never changed.
    fixed: list[Slot] = field(default_factory=list)
    # Per analyst: first date from which their roster before start_date is fully known
    # (normally the first day of the previous month's roster). Missing = unknown.
    history_known_from: dict[int, date] = field(default_factory=dict)
    # Assignments of the roster being regenerated (minimum-disruption objective).
    baseline: list[Slot] = field(default_factory=list)
    policy: Policy = field(default_factory=Policy)
    notes: list[str] = field(default_factory=list)

    def dates(self) -> list[date]:
        n = (self.end_date - self.start_date).days + 1
        return [self.start_date + timedelta(days=i) for i in range(n)]

    def selected_project_ids(self) -> set[int]:
        return {p for (p, _s, _d) in self.requirements}
