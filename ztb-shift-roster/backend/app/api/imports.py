"""Spreadsheet import (preview, then commit) and XLSX downloads."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy.orm import Session

from ..models import Roster
from ..schemas.common import StrictModel
from ..services import excel_import
from ..services.excel_export import TEMPLATES, export_roster, import_template
from .deps import get_db, get_or_404

router = APIRouter(tags=["excel"])
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ImportOptions(StrictModel):
    year: int | None = Field(default=None, ge=2000, le=2100)
    month: int | None = Field(default=None, ge=1, le=12)
    project_id: int | None = None
    status: Literal["historical", "draft"] = "historical"
    create_missing_analysts: bool = False
    update_existing: bool = False


class CommitIn(StrictModel):
    token: str = Field(max_length=64)
    mapping: dict[str, str | None] = Field(default_factory=dict, max_length=20)
    options: ImportOptions = Field(default_factory=ImportOptions)


def _download(data: bytes, filename: str) -> Response:
    return Response(content=data, media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/imports/preview")
async def preview(request: Request, file: UploadFile = File(...), kind: str = Form(...),
                  sheet: str | None = Form(default=None)):
    limit = request.app.state.settings.max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=413, detail=f"File larger than {limit // (1024 * 1024)} MB")
    if not data:
        raise HTTPException(status_code=422, detail="The file is empty")
    filename = (file.filename or "upload").replace("\\", "/").rsplit("/", 1)[-1][:200]
    return excel_import.preview(request.app.state.imports, kind, filename, data, sheet)


@router.post("/imports/commit")
def commit(body: CommitIn, request: Request, db: Session = Depends(get_db)):
    return excel_import.commit(db, request.app.state.imports, body.token, body.mapping,
                               body.options.model_dump())


@router.get("/imports/templates/{kind}.xlsx")
def template(kind: str):
    if kind not in TEMPLATES:
        raise HTTPException(status_code=404, detail="Unknown template")
    return _download(import_template(kind), f"shiftorbit-{kind}-template.xlsx")


@router.get("/rosters/{roster_id}/export.xlsx")
def export(roster_id: int, db: Session = Depends(get_db)):
    roster = get_or_404(db, Roster, roster_id)
    return _download(export_roster(db, roster), f"shiftorbit-roster-{roster.year}-{roster.month:02d}-v{roster.version}.xlsx")
