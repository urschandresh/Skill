"""Scheduling policies, availability exceptions, holidays and shift-code mappings."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Analyst, AvailabilityException, Holiday, Project, SchedulingPolicy, ShiftCodeMapping
from ..schemas.scheduling import (
    AvailabilityIn,
    AvailabilityOut,
    HolidayIn,
    HolidayOut,
    MappingIn,
    MappingOut,
    PolicyIn,
    PolicyOut,
)
from ..services.audit import record
from .deps import get_db, get_or_404

router = APIRouter(tags=["settings"])


# ---------------------------------------------------------------- policies


def _policy_data(body: PolicyIn) -> dict:
    data = body.model_dump()
    data["weights"] = body.weights.model_dump()
    return data


def _make_sole_default(db: Session, policy_id: int) -> None:
    db.execute(update(SchedulingPolicy).where(SchedulingPolicy.id != policy_id).values(is_default=False))


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(db: Session = Depends(get_db)):
    return list(db.scalars(select(SchedulingPolicy).order_by(SchedulingPolicy.name)))


@router.get("/policies/{policy_id}", response_model=PolicyOut)
def get_policy(policy_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, SchedulingPolicy, policy_id, "Policy")


@router.post("/policies", response_model=PolicyOut, status_code=201)
def create_policy(body: PolicyIn, db: Session = Depends(get_db)):
    policy = SchedulingPolicy(**_policy_data(body))
    db.add(policy)
    db.flush()
    if policy.is_default:
        _make_sole_default(db, policy.id)
    record(db, "create", "policy", policy.id)
    db.commit()
    return policy


@router.put("/policies/{policy_id}", response_model=PolicyOut)
def update_policy(policy_id: int, body: PolicyIn, db: Session = Depends(get_db)):
    policy = get_or_404(db, SchedulingPolicy, policy_id, "Policy")
    if policy.is_default and not body.is_default:
        raise HTTPException(status_code=422, detail="Mark another policy as default instead")
    for k, v in _policy_data(body).items():
        setattr(policy, k, v)
    if policy.is_default:
        _make_sole_default(db, policy.id)
    record(db, "update", "policy", policy.id)
    db.commit()
    return policy


@router.delete("/policies/{policy_id}", status_code=204)
def delete_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = get_or_404(db, SchedulingPolicy, policy_id, "Policy")
    if policy.is_default:
        raise HTTPException(status_code=409, detail="The default policy cannot be deleted")
    db.delete(policy)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- availability


@router.get("/availability", response_model=list[AvailabilityOut])
def list_availability(
    analyst_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
):
    q = select(AvailabilityException).order_by(AvailabilityException.date)
    if analyst_id is not None:
        q = q.where(AvailabilityException.analyst_id == analyst_id)
    if start is not None:
        q = q.where(AvailabilityException.date >= start)
    if end is not None:
        q = q.where(AvailabilityException.date <= end)
    return list(db.scalars(q))


@router.post("/availability", response_model=AvailabilityOut, status_code=201)
def create_availability(body: AvailabilityIn, db: Session = Depends(get_db)):
    get_or_404(db, Analyst, body.analyst_id)
    item = AvailabilityException(**body.model_dump())
    db.add(item)
    db.commit()
    return item


@router.put("/availability/{item_id}", response_model=AvailabilityOut)
def update_availability(item_id: int, body: AvailabilityIn, db: Session = Depends(get_db)):
    item = get_or_404(db, AvailabilityException, item_id, "Availability exception")
    get_or_404(db, Analyst, body.analyst_id)
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return item


@router.delete("/availability/{item_id}", status_code=204)
def delete_availability(item_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, AvailabilityException, item_id, "Availability exception"))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- holidays


@router.get("/holidays", response_model=list[HolidayOut])
def list_holidays(year: int | None = None, db: Session = Depends(get_db)):
    q = select(Holiday).order_by(Holiday.date)
    if year is not None:
        q = q.where(Holiday.date >= date(year, 1, 1), Holiday.date <= date(year, 12, 31))
    return list(db.scalars(q))


@router.post("/holidays", response_model=HolidayOut, status_code=201)
def create_holiday(body: HolidayIn, db: Session = Depends(get_db)):
    if body.project_id is not None:
        get_or_404(db, Project, body.project_id)
    item = Holiday(**body.model_dump())
    db.add(item)
    db.commit()
    return item


@router.put("/holidays/{item_id}", response_model=HolidayOut)
def update_holiday(item_id: int, body: HolidayIn, db: Session = Depends(get_db)):
    item = get_or_404(db, Holiday, item_id, "Holiday")
    if body.project_id is not None:
        get_or_404(db, Project, body.project_id)
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return item


@router.delete("/holidays/{item_id}", status_code=204)
def delete_holiday(item_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Holiday, item_id, "Holiday"))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- shift-code mappings


@router.get("/shift-code-mappings", response_model=list[MappingOut])
def list_mappings(db: Session = Depends(get_db)):
    return list(db.scalars(select(ShiftCodeMapping).order_by(ShiftCodeMapping.source_code)))


@router.post("/shift-code-mappings", response_model=MappingOut, status_code=201)
def create_mapping(body: MappingIn, db: Session = Depends(get_db)):
    item = ShiftCodeMapping(**body.model_dump())
    db.add(item)
    db.commit()
    return item


@router.put("/shift-code-mappings/{item_id}", response_model=MappingOut)
def update_mapping(item_id: int, body: MappingIn, db: Session = Depends(get_db)):
    item = get_or_404(db, ShiftCodeMapping, item_id, "Mapping")
    for k, v in body.model_dump().items():
        setattr(item, k, v)
    db.commit()
    return item


@router.delete("/shift-code-mappings/{item_id}", status_code=204)
def delete_mapping(item_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, ShiftCodeMapping, item_id, "Mapping"))
    db.commit()
    return Response(status_code=204)
