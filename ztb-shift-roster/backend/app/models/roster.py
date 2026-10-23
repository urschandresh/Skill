"""Rosters, assignments, day markers, solver runs and the audit log."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base
from .organization import Analyst, Project, ShiftTemplate, utcnow

# draft: editable; published: the official roster for the month (at most one);
# archived: a superseded published version; historical: imported from a previous roster file.
ROSTER_STATUSES = ("draft", "published", "archived", "historical")


class Roster(Base):
    __tablename__ = "rosters"
    id: Mapped[int] = mapped_column(primary_key=True)
    year: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_roster_id: Mapped[int | None] = mapped_column(
        ForeignKey("rosters.id", ondelete="SET NULL"), nullable=True
    )
    project_ids: Mapped[list] = mapped_column(JSON, default=list)
    analyst_ids: Mapped[list] = mapped_column(JSON, default=list)
    policy_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    solver_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    solver_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    assignments: Mapped[list[Assignment]] = relationship(
        back_populates="roster", cascade="all, delete-orphan", lazy="selectin"
    )
    markers: Mapped[list[RosterDayMarker]] = relationship(
        back_populates="roster", cascade="all, delete-orphan", lazy="selectin"
    )


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (
        UniqueConstraint(
            "roster_id", "analyst_id", "project_id", "shift_template_id", "date", name="uq_assignment"
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    roster_id: Mapped[int] = mapped_column(ForeignKey("rosters.id", ondelete="CASCADE"), index=True)
    analyst_id: Mapped[int] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    shift_template_id: Mapped[int] = mapped_column(ForeignKey("shift_templates.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date, index=True)  # the date the shift STARTS
    locked: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(String(16), default="solver")  # solver | manual | import
    override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    roster: Mapped[Roster] = relationship(back_populates="assignments")
    analyst: Mapped[Analyst] = relationship()
    project: Mapped[Project] = relationship()
    shift_template: Mapped[ShiftTemplate] = relationship()


class RosterDayMarker(Base):
    """Explicit non-working codes (WO, LEAVE, H), mainly from imported historical rosters.

    Generated rosters derive these from leave and holidays, so markers are optional there.
    """

    __tablename__ = "roster_day_markers"
    __table_args__ = (UniqueConstraint("roster_id", "analyst_id", "date", name="uq_marker"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    roster_id: Mapped[int] = mapped_column(ForeignKey("rosters.id", ondelete="CASCADE"), index=True)
    analyst_id: Mapped[int] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    code: Mapped[str] = mapped_column(String(8))

    roster: Mapped[Roster] = relationship(back_populates="markers")


JOB_STATES = ("queued", "running", "completed", "failed", "cancelled")


class SolverRun(Base):
    __tablename__ = "solver_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))  # generate | regenerate | simulate
    state: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    solver_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    roster_id: Mapped[int | None] = mapped_column(
        ForeignKey("rosters.id", ondelete="SET NULL"), nullable=True
    )
    base_roster_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Who-did-what trail. Stores entity IDs and action names, never personal details."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class AppMeta(Base):
    __tablename__ = "app_meta"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
