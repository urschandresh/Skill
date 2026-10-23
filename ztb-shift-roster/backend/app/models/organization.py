"""Projects, skills, shift templates, analysts and eligibility."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


project_skills = Table(
    "project_skills",
    Base.metadata,
    Column("project_id", ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)

analyst_skills = Table(
    "analyst_skills",
    Base.metadata,
    Column("analyst_id", ForeignKey("analysts.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)

template_skills = Table(
    "shift_template_skills",
    Base.metadata,
    Column("shift_template_id", ForeignKey("shift_templates.id", ondelete="CASCADE"), primary_key=True),
    Column("skill_id", ForeignKey("skills.id", ondelete="CASCADE"), primary_key=True),
)


class Skill(Base):
    __tablename__ = "skills"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    description: Mapped[str] = mapped_column(String(255), default="")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Kolkata")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    required_skills: Mapped[list[Skill]] = relationship(secondary=project_skills, lazy="selectin")
    shift_templates: Mapped[list[ShiftTemplate]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )
    staffing: Mapped[list[StaffingRequirement]] = relationship(
        back_populates="project", cascade="all, delete-orphan", lazy="selectin"
    )


class ShiftTemplate(Base):
    __tablename__ = "shift_templates"
    __table_args__ = (UniqueConstraint("project_id", "code", name="uq_template_project_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(8))
    name: Mapped[str] = mapped_column(String(64))
    start_time: Mapped[str] = mapped_column(String(5))  # "HH:MM" local to the project timezone
    end_time: Mapped[str] = mapped_column(String(5))  # end <= start means the shift ends next day
    is_night: Mapped[bool] = mapped_column(Boolean, default=False)
    color: Mapped[str] = mapped_column(String(7), default="#3b82f6")
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    project: Mapped[Project] = relationship(back_populates="shift_templates")
    required_skills: Mapped[list[Skill]] = relationship(secondary=template_skills, lazy="selectin")


class StaffingRequirement(Base):
    """Minimum (and optional maximum) headcount for a shift.

    Resolution order for a date: a row with ``specific_date`` beats a row with ``weekday``,
    which beats the default row (both null).
    """

    __tablename__ = "staffing_requirements"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    shift_template_id: Mapped[int] = mapped_column(ForeignKey("shift_templates.id", ondelete="CASCADE"))
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0 = Monday
    specific_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    min_staff: Mapped[int] = mapped_column(Integer, default=1)
    max_staff: Mapped[int | None] = mapped_column(Integer, nullable=True)

    project: Mapped[Project] = relationship(back_populates="staffing")
    shift_template: Mapped[ShiftTemplate] = relationship()


class Analyst(Base):
    __tablename__ = "analysts"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_code: Mapped[str] = mapped_column(String(32), unique=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_hours_per_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # {"preferred_shifts": ["M"], "avoid_shifts": ["N"], "preferred_off_days": [5, 6]}
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    skills: Mapped[list[Skill]] = relationship(secondary=analyst_skills, lazy="selectin")
    eligibility: Mapped[list[AnalystProject]] = relationship(
        back_populates="analyst", cascade="all, delete-orphan", lazy="selectin"
    )


class AnalystProject(Base):
    """An analyst may work on a project; ``allowed_shift_codes`` empty means all shifts."""

    __tablename__ = "analyst_projects"
    __table_args__ = (UniqueConstraint("analyst_id", "project_id", name="uq_analyst_project"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    analyst_id: Mapped[int] = mapped_column(ForeignKey("analysts.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    allowed_shift_codes: Mapped[list] = mapped_column(JSON, default=list)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)

    analyst: Mapped[Analyst] = relationship(back_populates="eligibility")
    project: Mapped[Project] = relationship()
