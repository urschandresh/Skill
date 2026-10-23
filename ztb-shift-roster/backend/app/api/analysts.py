"""Analysts and their project eligibility."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Analyst, AnalystProject, Assignment, Project
from ..schemas.organization import AnalystIn, AnalystOut, EligibilityIn
from ..services.audit import record
from .deps import get_db, get_or_404
from .organization import resolve_skills, used_in_protected_roster

router = APIRouter(tags=["analysts"])


def _apply_eligibility(db: Session, analyst: Analyst, items: list[EligibilityIn]) -> None:
    ids = [e.project_id for e in items]
    if ids:
        found = set(db.scalars(select(Project.id).where(Project.id.in_(ids))))
        missing = set(ids) - found
        if missing:
            raise HTTPException(status_code=422, detail=f"Unknown project ids: {sorted(missing)}")
    analyst.eligibility.clear()
    db.flush()
    for e in items:
        analyst.eligibility.append(
            AnalystProject(project_id=e.project_id, allowed_shift_codes=list(e.allowed_shift_codes), is_primary=e.is_primary)
        )


@router.get("/analysts", response_model=list[AnalystOut])
def list_analysts(include_inactive: bool = True, project_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Analyst).order_by(Analyst.full_name)
    if not include_inactive:
        q = q.where(Analyst.active)
    if project_id is not None:
        q = q.join(AnalystProject).where(AnalystProject.project_id == project_id)
    return [AnalystOut.from_model(a) for a in db.scalars(q)]


@router.get("/analysts/{analyst_id}", response_model=AnalystOut)
def get_analyst(analyst_id: int, db: Session = Depends(get_db)):
    return AnalystOut.from_model(get_or_404(db, Analyst, analyst_id))


@router.post("/analysts", response_model=AnalystOut, status_code=201)
def create_analyst(body: AnalystIn, db: Session = Depends(get_db)):
    analyst = Analyst(
        **body.model_dump(exclude={"skill_ids", "eligibility", "preferences"}),
        preferences=body.preferences.model_dump(),
        skills=resolve_skills(db, body.skill_ids),
    )
    db.add(analyst)
    db.flush()
    _apply_eligibility(db, analyst, body.eligibility)
    record(db, "create", "analyst", analyst.id)
    db.commit()
    db.refresh(analyst)
    return AnalystOut.from_model(analyst)


@router.put("/analysts/{analyst_id}", response_model=AnalystOut)
def update_analyst(analyst_id: int, body: AnalystIn, db: Session = Depends(get_db)):
    analyst = get_or_404(db, Analyst, analyst_id)
    for k, v in body.model_dump(exclude={"skill_ids", "eligibility", "preferences"}).items():
        setattr(analyst, k, v)
    analyst.preferences = body.preferences.model_dump()
    analyst.skills = resolve_skills(db, body.skill_ids)
    _apply_eligibility(db, analyst, body.eligibility)
    record(db, "update", "analyst", analyst.id)
    db.commit()
    db.refresh(analyst)
    return AnalystOut.from_model(analyst)


@router.put("/analysts/{analyst_id}/eligibility", response_model=AnalystOut)
def set_eligibility(analyst_id: int, body: list[EligibilityIn], db: Session = Depends(get_db)):
    analyst = get_or_404(db, Analyst, analyst_id)
    if len({e.project_id for e in body}) != len(body):
        raise HTTPException(status_code=422, detail="each project may appear only once")
    _apply_eligibility(db, analyst, body)
    record(db, "update_eligibility", "analyst", analyst.id)
    db.commit()
    db.refresh(analyst)
    return AnalystOut.from_model(analyst)


@router.delete("/analysts/{analyst_id}", status_code=204)
def delete_analyst(analyst_id: int, db: Session = Depends(get_db)):
    analyst = get_or_404(db, Analyst, analyst_id)
    if used_in_protected_roster(db, Assignment.analyst_id, analyst_id):
        raise HTTPException(
            status_code=409,
            detail="Analyst appears in published or historical rosters; deactivate instead, "
            "or use Settings > Delete all local data.",
        )
    db.delete(analyst)
    record(db, "delete", "analyst", analyst_id)
    db.commit()
    return Response(status_code=204)
