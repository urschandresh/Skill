"""Skills, projects, shift templates and staffing requirements."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Assignment, Project, Roster, ShiftTemplate, Skill, StaffingRequirement
from ..schemas.organization import (
    ProjectCreate,
    ProjectIn,
    ProjectOut,
    ShiftTemplateIn,
    ShiftTemplateOut,
    SkillIn,
    SkillOut,
    StaffingIn,
    StaffingOut,
)
from ..services.audit import record
from ..services.seed import DEFAULT_SHIFT_TEMPLATES
from .deps import get_db, get_or_404

router = APIRouter(tags=["organization"])

PROTECTED_ROSTER_STATUSES = ("published", "archived", "historical")


def resolve_skills(session: Session, ids: list[int]) -> list[Skill]:
    if not ids:
        return []
    skills = list(session.scalars(select(Skill).where(Skill.id.in_(ids))))
    missing = set(ids) - {s.id for s in skills}
    if missing:
        raise HTTPException(status_code=422, detail=f"Unknown skill ids: {sorted(missing)}")
    return skills


def used_in_protected_roster(session: Session, column, value: int) -> int:
    return session.scalar(
        select(func.count(Assignment.id))
        .join(Roster, Roster.id == Assignment.roster_id)
        .where(column == value, Roster.status.in_(PROTECTED_ROSTER_STATUSES))
    ) or 0


# ---------------------------------------------------------------- skills


@router.get("/skills", response_model=list[SkillOut])
def list_skills(db: Session = Depends(get_db)):
    return list(db.scalars(select(Skill).order_by(Skill.name)))


@router.post("/skills", response_model=SkillOut, status_code=201)
def create_skill(body: SkillIn, db: Session = Depends(get_db)):
    skill = Skill(**body.model_dump())
    db.add(skill)
    db.commit()
    return skill


@router.put("/skills/{skill_id}", response_model=SkillOut)
def update_skill(skill_id: int, body: SkillIn, db: Session = Depends(get_db)):
    skill = get_or_404(db, Skill, skill_id)
    for k, v in body.model_dump().items():
        setattr(skill, k, v)
    db.commit()
    return skill


@router.delete("/skills/{skill_id}", status_code=204)
def delete_skill(skill_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, Skill, skill_id))
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- projects


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(include_inactive: bool = True, db: Session = Depends(get_db)):
    q = select(Project).order_by(Project.code)
    if not include_inactive:
        q = q.where(Project.active)
    return [ProjectOut.from_model(p) for p in db.scalars(q)]


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    return ProjectOut.from_model(get_or_404(db, Project, project_id))


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db)):
    data = body.model_dump(exclude={"required_skill_ids", "create_default_shifts", "default_min_staff"})
    project = Project(**data, required_skills=resolve_skills(db, body.required_skill_ids))
    db.add(project)
    db.flush()
    if body.create_default_shifts:
        for tpl in DEFAULT_SHIFT_TEMPLATES:
            t = ShiftTemplate(project_id=project.id, **tpl)
            db.add(t)
            db.flush()
            db.add(StaffingRequirement(project_id=project.id, shift_template_id=t.id, min_staff=body.default_min_staff))
    record(db, "create", "project", project.id)
    db.commit()
    db.refresh(project)
    return ProjectOut.from_model(project)


@router.put("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectIn, db: Session = Depends(get_db)):
    project = get_or_404(db, Project, project_id)
    for k, v in body.model_dump(exclude={"required_skill_ids"}).items():
        setattr(project, k, v)
    project.required_skills = resolve_skills(db, body.required_skill_ids)
    record(db, "update", "project", project.id)
    db.commit()
    db.refresh(project)
    return ProjectOut.from_model(project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = get_or_404(db, Project, project_id)
    if used_in_protected_roster(db, Assignment.project_id, project_id):
        raise HTTPException(
            status_code=409,
            detail="Project appears in published or historical rosters; deactivate it instead.",
        )
    db.delete(project)
    record(db, "delete", "project", project_id)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- shift templates


@router.post("/projects/{project_id}/shift-templates", response_model=ShiftTemplateOut, status_code=201)
def create_template(project_id: int, body: ShiftTemplateIn, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id)
    tpl = ShiftTemplate(
        project_id=project_id,
        **body.model_dump(exclude={"required_skill_ids"}),
        required_skills=resolve_skills(db, body.required_skill_ids),
    )
    db.add(tpl)
    record(db, "create", "shift_template", project_id)
    db.commit()
    db.refresh(tpl)
    return ShiftTemplateOut.from_model(tpl)


@router.put("/shift-templates/{template_id}", response_model=ShiftTemplateOut)
def update_template(template_id: int, body: ShiftTemplateIn, db: Session = Depends(get_db)):
    tpl = get_or_404(db, ShiftTemplate, template_id, "Shift template")
    for k, v in body.model_dump(exclude={"required_skill_ids"}).items():
        setattr(tpl, k, v)
    tpl.required_skills = resolve_skills(db, body.required_skill_ids)
    record(db, "update", "shift_template", template_id)
    db.commit()
    db.refresh(tpl)
    return ShiftTemplateOut.from_model(tpl)


@router.delete("/shift-templates/{template_id}", status_code=204)
def delete_template(template_id: int, db: Session = Depends(get_db)):
    tpl = get_or_404(db, ShiftTemplate, template_id, "Shift template")
    if used_in_protected_roster(db, Assignment.shift_template_id, template_id):
        raise HTTPException(
            status_code=409,
            detail="Shift template is used by published or historical rosters; deactivate it instead.",
        )
    db.delete(tpl)
    record(db, "delete", "shift_template", template_id)
    db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- staffing


def _check_template(db: Session, project_id: int, template_id: int) -> None:
    tpl = db.get(ShiftTemplate, template_id)
    if tpl is None or tpl.project_id != project_id:
        raise HTTPException(status_code=422, detail="shift_template_id does not belong to this project")


@router.get("/projects/{project_id}/staffing", response_model=list[StaffingOut])
def list_staffing(project_id: int, db: Session = Depends(get_db)):
    return get_or_404(db, Project, project_id).staffing


@router.post("/projects/{project_id}/staffing", response_model=StaffingOut, status_code=201)
def create_staffing(project_id: int, body: StaffingIn, db: Session = Depends(get_db)):
    get_or_404(db, Project, project_id)
    _check_template(db, project_id, body.shift_template_id)
    duplicate = db.scalar(
        select(StaffingRequirement).where(
            StaffingRequirement.project_id == project_id,
            StaffingRequirement.shift_template_id == body.shift_template_id,
            StaffingRequirement.weekday.is_(None) if body.weekday is None else StaffingRequirement.weekday == body.weekday,
            StaffingRequirement.specific_date.is_(None)
            if body.specific_date is None
            else StaffingRequirement.specific_date == body.specific_date,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="A requirement for this shift and day already exists")
    req = StaffingRequirement(project_id=project_id, **body.model_dump())
    db.add(req)
    db.commit()
    return req


@router.put("/staffing/{req_id}", response_model=StaffingOut)
def update_staffing(req_id: int, body: StaffingIn, db: Session = Depends(get_db)):
    req = get_or_404(db, StaffingRequirement, req_id, "Staffing requirement")
    _check_template(db, req.project_id, body.shift_template_id)
    for k, v in body.model_dump().items():
        setattr(req, k, v)
    db.commit()
    return req


@router.delete("/staffing/{req_id}", status_code=204)
def delete_staffing(req_id: int, db: Session = Depends(get_db)):
    db.delete(get_or_404(db, StaffingRequirement, req_id, "Staffing requirement"))
    db.commit()
    return Response(status_code=204)
