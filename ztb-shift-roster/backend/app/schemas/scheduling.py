from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, model_validator

from .common import HHMM, LongText, Name, OrmModel, ShiftCode, ShortText, StrictModel, minutes_of


class Weights(StrictModel):
    fair_nights: int = Field(default=10, ge=0, le=1000)
    fair_weekends: int = Field(default=8, ge=0, le=1000)
    balanced_hours: int = Field(default=5, ge=0, le=1000)
    preferences: int = Field(default=2, ge=0, le=1000)
    shift_changes: int = Field(default=3, ge=0, le=1000)
    disruption: int = Field(default=20, ge=0, le=1000)


class PolicyFields(StrictModel):
    working_days_per_week: int = Field(default=5, ge=1, le=7)
    week_start_day: int = Field(default=0, ge=0, le=6)
    weekly_mode: Literal["exact", "max"] = "exact"
    max_hours_per_week: int = Field(default=48, ge=1, le=112)
    max_consecutive_work_days: int = Field(default=6, ge=1, le=14)
    max_consecutive_nights: int = Field(default=5, ge=0, le=14)
    min_rest_hours: int = Field(default=11, ge=0, le=24)
    one_shift_per_day: bool = True
    leave_counts_as_working_day: bool = True
    solver_time_limit_seconds: int = Field(default=30, ge=1, le=600)
    weights: Weights = Field(default_factory=Weights)


class PolicyIn(PolicyFields):
    name: Name = Field(max_length=64)
    is_default: bool = False


class PolicyOut(OrmModel):
    id: int
    name: str
    is_default: bool
    working_days_per_week: int
    week_start_day: int
    weekly_mode: str
    max_hours_per_week: int
    max_consecutive_work_days: int
    max_consecutive_nights: int
    min_rest_hours: int
    one_shift_per_day: bool
    leave_counts_as_working_day: bool
    solver_time_limit_seconds: int
    weights: dict


class LeaveIn(StrictModel):
    analyst_id: int
    start_date: date
    end_date: date
    leave_type: Literal["annual", "sick", "casual", "comp_off", "unpaid", "other"] = "annual"
    partial_day: bool = False
    start_time: HHMM | None = None
    end_time: HHMM | None = None
    reason: LongText = ""

    @model_validator(mode="after")
    def _check(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("leave cannot exceed 366 days")
        if self.partial_day:
            if self.start_date != self.end_date:
                raise ValueError("partial-day leave must start and end on the same date")
            if self.start_time is None or self.end_time is None:
                raise ValueError("partial-day leave needs start_time and end_time")
            if minutes_of(self.end_time) <= minutes_of(self.start_time):
                raise ValueError("partial-day leave end_time must be after start_time")
        elif self.start_time is not None or self.end_time is not None:
            raise ValueError("start_time/end_time are only allowed for partial-day leave")
        return self


class LeaveDecision(StrictModel):
    note: LongText = ""


class LeaveOut(OrmModel):
    id: int
    analyst_id: int
    start_date: date
    end_date: date
    leave_type: str
    partial_day: bool
    start_time: str | None
    end_time: str | None
    status: str
    reason: str
    decision_note: str
    source: str
    created_at: datetime
    decided_at: datetime | None


class AvailabilityIn(StrictModel):
    analyst_id: int
    date: date
    kind: Literal["unavailable", "block_shifts"] = "unavailable"
    shift_codes: list[ShiftCode] = Field(default_factory=list, max_length=20)
    note: ShortText = ""

    @model_validator(mode="after")
    def _check(self):
        if self.kind == "block_shifts" and not self.shift_codes:
            raise ValueError("block_shifts needs at least one shift code")
        return self


class AvailabilityOut(OrmModel):
    id: int
    analyst_id: int
    date: date
    kind: str
    shift_codes: list[str]
    note: str


class HolidayIn(StrictModel):
    date: date
    name: Name
    project_id: int | None = None
    blocks_work: bool = False


class HolidayOut(OrmModel):
    id: int
    date: date
    name: str
    project_id: int | None
    blocks_work: bool


class MappingIn(StrictModel):
    source_code: str = Field(pattern=r"^[A-Za-z0-9/_-]{1,16}$")
    target_kind: Literal["shift", "WO", "LEAVE", "H"]
    target_shift_code: ShiftCode | None = None
    description: ShortText = ""

    @model_validator(mode="after")
    def _check(self):
        self.source_code = self.source_code.upper()
        if self.target_kind == "shift" and not self.target_shift_code:
            raise ValueError("a shift mapping needs target_shift_code")
        if self.target_kind != "shift":
            self.target_shift_code = None
        return self


class MappingOut(OrmModel):
    id: int
    source_code: str
    target_kind: str
    target_shift_code: str | None
    description: str
