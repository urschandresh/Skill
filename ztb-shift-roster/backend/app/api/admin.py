"""Backup, restore, complete data deletion, demo data and the audit trail."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AuditLog
from ..schemas.common import StrictModel
from ..services import backup
from ..services.audit import record
from ..services.demo import load_demo_data
from .deps import get_db

router = APIRouter(prefix="/admin", tags=["admin"])
MAX_RESTORE_BYTES = 200 * 1024 * 1024


class DeleteAllIn(StrictModel):
    confirm: str = Field(max_length=64)


@router.get("/backups")
def list_backups(request: Request):
    return backup.list_backups(request.app.state.settings)


@router.post("/backups", status_code=201)
def create_backup(request: Request, db: Session = Depends(get_db)):
    path = backup.create_backup(request.app.state.settings)
    record(db, "backup", "system", path.name)
    db.commit()
    return {"name": path.name, "size_bytes": path.stat().st_size, "created_at": None}


@router.get("/backups/{name}")
def download_backup(name: str, request: Request):
    path = backup.backup_path(request.app.state.settings, name)
    return FileResponse(path, media_type="application/vnd.sqlite3", filename=path.name)


@router.post("/restore")
async def restore(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    data = await file.read(MAX_RESTORE_BYTES + 1)
    if len(data) > MAX_RESTORE_BYTES:
        raise HTTPException(status_code=413, detail="Backup file too large")
    st = request.app.state
    result = backup.restore_backup(st.settings, st.engine, db, data)
    with st.session_factory() as s:
        record(s, "restore", "system", result["safety_backup"])
        s.commit()
    return result


@router.post("/delete-all-data")
def delete_all(body: DeleteAllIn, request: Request, db: Session = Depends(get_db)):
    st = request.app.state
    return backup.delete_all_data(st.settings, st.engine, db, body.confirm)


@router.post("/demo-data", status_code=201)
def demo_data(db: Session = Depends(get_db)):
    return load_demo_data(db)


@router.get("/audit")
def audit(limit: int = 200, db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 1000))))
    return [{"ts": r.ts, "action": r.action, "entity": r.entity, "entity_id": r.entity_id, "detail": r.detail}
            for r in rows]
