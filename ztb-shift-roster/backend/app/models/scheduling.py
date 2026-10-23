"""Scheduling policies, leave, availability exceptions, holidays and code mappings."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .organization import Analyst, utcnow

DEFAULT_WEIGHTS = {
    "fair_nights": 10,
    "fair_weekends": 8,
    "balanced_hours": 5,
    "preferences": 2,
    "shift_changes": 3,
    "disruption": 20,
}


class SchedulingPolicy(Base):
    __tablename__ = "scheduling_policies"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    working_days_per_week: Mapped[int] = mapped_column(Integer, default=5)
    week_start_day: Mapped[int] = mapped_column(Integer, default=0)  # 0 = Monday
    # "exact": analysts work exactly working_days_per_week (less leave) in every fully known week.
    # "max": working_days_per_week is only an upper bound.
    weekly_mode: Mapped[str] = mapped_column(String(8), default="exact")
    max_hours_per_week: Mapped[int] = mapped_column(Integer, default=48)
    max_consecutive_work_days: Mapped[int] = mapped_column(Integer, default=6)
    max_consecutive_nights: Mapped[int] = mapped_column(Integer, default=5)
    min_rest_hours: Mapped[int] = mapped_column(Integer, default=11)
    one_shift_per_day: Mapped[bool] = mapped_column(Boolean, default=True)
    leave_counts_as_working_day: Mapped[bool] = mapped_column(Boolean, default=True)
    solver_time_limit_seconds: Mapped[int] = mapped_column(Integer, default=30)
    weights: Mapped[dict] = mapped_column(JSON, default=lambda: dict(DEFAULT_WEIGHTS))


LEAVE_STATUSES = ("pending", "approved", "rejected", "cancelled")
LEAVE_TYPES = ("annual", "sick", "casual", "comp_off", "unpaid", "other")


class LeaveRequest(Base):
    __tablename__ = "leave_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    analyst_id: Mapped[int] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"), index=True)
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    leave_type: Mapped[str] = mapped_column(String(16), default="annual")
    # Partial-day leave covers [start_time, end_time) on a single date, local to the project timezone.
    partial_day: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    decision_note: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    analyst: Mapped[Analyst] = relationship()


class AvailabilityException(Base):
    """``unavailable`` blocks the whole day; ``block_shifts`` blocks only the listed shift codes."""

    __tablename__ = "availability_exceptions"
    id: Mapped[int] = mapped_column(primary_key=True)
    analyst_id: Mapped[int] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(16), default="unavailable")
    shift_codes: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(String(255), default="")

    analyst: Mapped[Analyst] = relationship()


class Holiday(Base):
    """A calendar holiday. SOC coverage normally continues, so it only blocks work when
    ``blocks_work`` is set (then it behaves like approved leave for everyone in scope)."""

    __tablename__ = "holidays"
    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    name: Mapped[str] = mapped_column(String(120))
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    blocks_work: Mapped[bool] = mapped_column(Boolean, default=False)


MAPPING_KINDS = ("shift", "WO", "LEAVE", "H")


class ShiftCodeMapping(Base):
    """Maps a code found in historical/imported rosters to a ShiftOrbit meaning."""

    __tablename__ = "shift_code_mappings"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_code: Mapped[str] = mapped_column(String(16), unique=True)
    target_kind: Mapped[str] = mapped_column(String(8))
    target_shift_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    description: Mapped[str] = mapped_column(String(255), default="")
