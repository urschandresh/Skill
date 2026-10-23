from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .common import LongText, StrictModel
from .scheduling import Weights


class PolicyOverrides(StrictModel):
    working_days_per_week: int | None = Field(default=None, ge=1, le=7)
    week_start_day: int | None = Field(default=None, ge=0, le=6)
    weekly_mode: Literal["exact", "max"] | None = None
    max_hours_per_week: int | None = Field(default=None, ge=1, le=112)
    max_consecutive_work_days: int | None = Field(default=None, ge=1, le=14)
    max_consecutive_nights: int | None = Field(default=None, ge=0, le=14)
    min_rest_hours: int | None = Field(default=None, ge=0, le=24)
    one_shift_per_day: bool | None = None
    leave_counts_as_working_day: bool | None = None
    weights: Weights | None = None

    def as_dict(self) -> dict:
        data = self.model_dump(exclude_none=True)
        return data


class SlotIn(StrictModel):
    analyst_id: int
    project_id: int
    shift_template_id: int
    date: date


class GenerateIn(StrictModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)
    project_ids: list[int] = Field(min_length=1, max_length=50)
    analyst_ids: list[int] | None = Field(default=None, max_length=500)
    policy_id: int | None = None
    policy_overrides: PolicyOverrides = Field(default_factory=PolicyOverrides)
    time_limit_seconds: int | None = Field(default=None, ge=1, le=600)
    locked: list[SlotIn] = Field(default_factory=list, max_length=5000)
    simulate_pending_leave_ids: list[int] = Field(default_factory=list, max_length=200)


class RegenerateIn(StrictModel):
    window_start: date | None = None
    window_end: date | None = None
    time_limit_seconds: int | None = Field(default=None, ge=1, le=600)
    simulate: bool = False
    simulate_pending_leave_ids: list[int] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _check(self):
        if (self.window_start is None) != (self.window_end is None):
            raise ValueError("give both window_start and window_end, or neither")
        if self.window_start and self.window_end and self.window_end < self.window_start:
            raise ValueError("window_end must be on or after window_start")
        return self


class _SlotOp(StrictModel):
    analyst_id: int
    project_id: int
    shift_template_id: int
    date: date


class AddOp(_SlotOp):
    op: Literal["add"]
    locked: bool = False


class RemoveOp(_SlotOp):
    op: Literal["remove"]


class LockOp(_SlotOp):
    op: Literal["lock", "unlock"]


class MoveOp(StrictModel):
    op: Literal["move"]
    from_analyst_id: int
    from_project_id: int
    from_shift_template_id: int
    from_date: date
    to_analyst_id: int
    to_project_id: int
    to_shift_template_id: int
    to_date: date


Op = Annotated[AddOp | RemoveOp | LockOp | MoveOp, Field(discriminator="op")]


class ChangesIn(StrictModel):
    ops: list[Op] = Field(min_length=1, max_length=500)
    dry_run: bool = False
    override_reason: LongText | None = Field(default=None, min_length=5)


class PublishIn(StrictModel):
    override_reason: LongText | None = Field(default=None, min_length=5)


class RosterPatch(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    notes: LongText | None = None
