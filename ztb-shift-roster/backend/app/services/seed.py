"""Reference data every installation needs. Contains no people or production data."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DEFAULT_WEIGHTS, SchedulingPolicy, ShiftCodeMapping

# Default shift templates created with a new project (times are local to the project timezone).
DEFAULT_SHIFT_TEMPLATES = [
    {"code": "M", "name": "Morning", "start_time": "06:00", "end_time": "15:00", "is_night": False, "color": "#38bdf8"},
    {"code": "A", "name": "Afternoon", "start_time": "14:00", "end_time": "23:00", "is_night": False, "color": "#f59e0b"},
    {"code": "N", "name": "Night", "start_time": "22:00", "end_time": "07:00", "is_night": True, "color": "#6366f1"},
]

# Codes understood when importing previous SOC rosters. D and AN are mapped to shift codes of
# the same name; create matching shift templates (with the real timings) before importing
# rosters that use them. Every mapping is editable in Settings.
DEFAULT_CODE_MAPPINGS = [
    ("M", "shift", "M", "Morning shift"),
    ("A", "shift", "A", "Afternoon shift"),
    ("N", "shift", "N", "Night shift"),
    ("D", "shift", "D", "Day/general shift (timing set by the project's D template)"),
    ("AN", "shift", "AN", "AN shift (timing set by the project's AN template)"),
    ("WO", "WO", None, "Weekly off"),
    ("OFF", "WO", None, "Weekly off (alternate spelling)"),
    ("LEAVE", "LEAVE", None, "Leave"),
    ("L", "LEAVE", None, "Leave (short form)"),
    ("PL", "LEAVE", None, "Planned leave"),
    ("H", "H", None, "Holiday"),
]


def seed_reference_data(session: Session) -> None:
    if session.scalar(select(SchedulingPolicy).limit(1)) is None:
        session.add(
            SchedulingPolicy(
                name="Standard SOC 5x2",
                is_default=True,
                weights=dict(DEFAULT_WEIGHTS),
            )
        )
    existing = set(session.scalars(select(ShiftCodeMapping.source_code)))
    if not existing:
        for source, kind, target, desc in DEFAULT_CODE_MAPPINGS:
            session.add(
                ShiftCodeMapping(
                    source_code=source, target_kind=kind, target_shift_code=target, description=desc
                )
            )
