from __future__ import annotations

from datetime import date

from pydantic import Field, model_validator

from .common import (
    HHMM,
    Color,
    Email,
    EmployeeCode,
    LongText,
    Name,
    OrmModel,
    ProjectCode,
    ShiftCode,
    ShortText,
    StrictModel,
    TimeZoneName,
    Weekday,
    shift_duration_minutes,
)


class SkillIn(StrictModel):
    name: Name = Field(max_length=64)
    description: ShortText = ""


class SkillOut(OrmModel):
    id: int
    name: str
    description: str


class ShiftTemplateIn(StrictModel):
    code: ShiftCode
    name: Name = Field(max_length=64)
    start_time: HHMM
    end_time: HHMM
    is_night: bool = False
    color: Color = "#3b82f6"
    active: bool = True
    required_skill_ids: list[int] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _duration(self):
        minutes = shift_duration_minutes(self.start_time, self.end_time)
        if not 60 <= minutes <= 16 * 60:
            raise ValueError("shift duration must be between 1 and 16 hours")
        return self


class ShiftTemplateOut(OrmModel):
    id: int
    project_id: int
    code: str
    name: str
    start_time: str
    end_time: str
    is_night: bool
    color: str
    active: bool
    duration_minutes: int = 0
    overnight: bool = False
    required_skill_ids: list[int] = Field(default_factory=list)

    @classmethod
    def from_model(cls, t) -> ShiftTemplateOut:
        minutes = shift_duration_minutes(t.start_time, t.end_time)
        return cls(
            id=t.id,
            project_id=t.project_id,
            code=t.code,
            name=t.name,
            start_time=t.start_time,
            end_time=t.end_time,
            is_night=t.is_night,
            color=t.color,
            active=t.active,
            duration_minutes=minutes,
            overnight=t.end_time <= t.start_time,
            required_skill_ids=[s.id for s in t.required_skills],
        )


class StaffingIn(StrictModel):
    shift_template_id: int
    weekday: Weekday | None = None
    specific_date: date | None = None
    min_staff: int = Field(default=1, ge=0, le=100)
    max_staff: int | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def _check(self):
        if self.weekday is not None and self.specific_date is not None:
            raise ValueError("set either weekday or specific_date, not both")
        if self.max_staff is not None and self.max_staff < self.min_staff:
            raise ValueError("max_staff must be >= min_staff")
        return self


class StaffingOut(OrmModel):
    id: int
    project_id: int
    shift_template_id: int
    weekday: int | None
    specific_date: date | None
    min_staff: int
    max_staff: int | None


class ProjectIn(StrictModel):
    code: ProjectCode
    name: Name
    description: LongText = ""
    timezone: TimeZoneName = "Asia/Kolkata"
    active: bool = True
    required_skill_ids: list[int] = Field(default_factory=list, max_length=50)


class ProjectCreate(ProjectIn):
    create_default_shifts: bool = True
    default_min_staff: int = Field(default=1, ge=0, le=100)


class ProjectOut(OrmModel):
    id: int
    code: str
    name: str
    description: str
    timezone: str
    active: bool
    required_skill_ids: list[int]
    shift_templates: list[ShiftTemplateOut]
    staffing: list[StaffingOut]

    @classmethod
    def from_model(cls, p) -> ProjectOut:
        return cls(
            id=p.id,
            code=p.code,
            name=p.name,
            description=p.description,
            timezone=p.timezone,
            active=p.active,
            required_skill_ids=[s.id for s in p.required_skills],
            shift_templates=[ShiftTemplateOut.from_model(t) for t in sorted(p.shift_templates, key=lambda t: t.start_time)],
            staffing=[StaffingOut.model_validate(s) for s in p.staffing],
        )


class Preferences(StrictModel):
    preferred_shifts: list[ShiftCode] = Field(default_factory=list, max_length=10)
    avoid_shifts: list[ShiftCode] = Field(default_factory=list, max_length=10)
    preferred_off_days: list[Weekday] = Field(default_factory=list, max_length=7)


class EligibilityIn(StrictModel):
    project_id: int
    allowed_shift_codes: list[ShiftCode] = Field(default_factory=list, max_length=20)
    is_primary: bool = False


class EligibilityOut(OrmModel):
    project_id: int
    allowed_shift_codes: list[str]
    is_primary: bool


class AnalystIn(StrictModel):
    employee_code: EmployeeCode
    full_name: Name
    email: Email | None = None
    active: bool = True
    max_hours_per_week: int | None = Field(default=None, ge=1, le=84)
    preferences: Preferences = Field(default_factory=Preferences)
    notes: LongText = ""
    skill_ids: list[int] = Field(default_factory=list, max_length=50)
    eligibility: list[EligibilityIn] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _unique_projects(self):
        ids = [e.project_id for e in self.eligibility]
        if len(ids) != len(set(ids)):
            raise ValueError("each project may appear only once in eligibility")
        if sum(1 for e in self.eligibility if e.is_primary) > 1:
            raise ValueError("only one primary project is allowed")
        return self


class AnalystOut(OrmModel):
    id: int
    employee_code: str
    full_name: str
    email: str | None
    active: bool
    max_hours_per_week: int | None
    preferences: dict
    notes: str
    skill_ids: list[int]
    eligibility: list[EligibilityOut]

    @classmethod
    def from_model(cls, a) -> AnalystOut:
        return cls(
            id=a.id,
            employee_code=a.employee_code,
            full_name=a.full_name,
            email=a.email,
            active=a.active,
            max_hours_per_week=a.max_hours_per_week,
            preferences=a.preferences or {},
            notes=a.notes,
            skill_ids=[s.id for s in a.skills],
            eligibility=[EligibilityOut.model_validate(e) for e in a.eligibility],
        )
