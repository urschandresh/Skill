from __future__ import annotations

import re
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
RESERVED_CODES = {"WO", "LEAVE", "H", "OFF"}


def _clean_text(value: str) -> str:
    value = value.strip()
    if _CONTROL.search(value):
        raise ValueError("must not contain control characters")
    return value


def _hhmm(value: str) -> str:
    if not _HHMM.match(value):
        raise ValueError("must be a 24-hour time HH:MM")
    return value


def _timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone {value!r}") from exc
    return value


def _shift_code(value: str) -> str:
    value = value.strip().upper()
    if value in RESERVED_CODES:
        raise ValueError(f"{value} is reserved for non-working days")
    return value


def _upper(value: str) -> str:
    return value.strip().upper()


Text = Annotated[str, AfterValidator(_clean_text)]
Name = Annotated[str, Field(min_length=1, max_length=120), AfterValidator(_clean_text)]
ShortText = Annotated[str, Field(max_length=255), AfterValidator(_clean_text)]
LongText = Annotated[str, Field(max_length=4000), AfterValidator(_clean_text)]
HHMM = Annotated[str, AfterValidator(_hhmm)]
TimeZoneName = Annotated[str, Field(max_length=64), AfterValidator(_timezone)]
ShiftCode = Annotated[str, Field(pattern=r"^\s*[A-Za-z][A-Za-z0-9]{0,7}\s*$"), AfterValidator(_shift_code)]
ProjectCode = Annotated[str, Field(pattern=r"^\s*[A-Za-z0-9][A-Za-z0-9_-]{0,15}\s*$"), AfterValidator(_upper)]
EmployeeCode = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]
Email = Annotated[str, Field(max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")]
Weekday = Annotated[int, Field(ge=0, le=6)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_max_length=4000)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def minutes_of(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def shift_duration_minutes(start: str, end: str) -> int:
    """Duration of a shift; an end at or before the start means it ends the next day."""
    s, e = minutes_of(start), minutes_of(end)
    if e <= s:
        e += 24 * 60
    return e - s
