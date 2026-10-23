"""Local backup, restore and complete data deletion for the SQLite database."""

from __future__ import annotations

import re
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..config import SCHEMA_VERSION, Settings
from ..db import Base
from ..models import SolverRun
from .seed import seed_reference_data

BACKUP_NAME = re.compile(r"^shiftorbit-\d{8}-\d{6}(-[a-z-]+)?\.db$")
REQUIRED_TABLES = {"app_meta", "projects", "analysts", "rosters", "assignments", "leave_requests"}
DELETE_CONFIRMATION = "DELETE ALL DATA"


def _jobs_running(session: Session) -> bool:
    return session.scalar(select(SolverRun.id).where(SolverRun.state.in_(("queued", "running"))).limit(1)) is not None


def create_backup(settings: Settings, label: str = "") -> Path:
    settings.backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-{label}" if label else ""
    target = settings.backup_dir / f"shiftorbit-{stamp}{suffix}.db"
    for extra in "bcdefgh":  # two backups in the same second
        if not target.exists():
            break
        target = settings.backup_dir / f"shiftorbit-{stamp}{suffix}-{extra}.db"
    else:
        raise HTTPException(status_code=409, detail="Too many backups this second; try again")
    src = sqlite3.connect(settings.database_path)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)  # consistent online copy, safe while the app is running
    finally:
        dst.close()
        src.close()
    return target


def list_backups(settings: Settings) -> list[dict]:
    if not settings.backup_dir.is_dir():
        return []
    items = []
    for p in sorted(settings.backup_dir.glob("shiftorbit-*.db"), reverse=True):
        if BACKUP_NAME.match(p.name):
            st = p.stat()
            items.append({"name": p.name, "size_bytes": st.st_size,
                          "created_at": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    return items


def backup_path(settings: Settings, name: str) -> Path:
    if not BACKUP_NAME.match(name):
        raise HTTPException(status_code=400, detail="Invalid backup name")
    path = (settings.backup_dir / name).resolve()
    if path.parent != settings.backup_dir.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Backup not found")
    return path


def _check_backup_file(path: Path) -> None:
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=422, detail="Not a SQLite database") from exc
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise HTTPException(status_code=422, detail="Backup file failed SQLite integrity check")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES <= tables:
            raise HTTPException(status_code=422, detail="File is not a ShiftOrbit database")
        row = con.execute("SELECT value FROM app_meta WHERE key='schema_version'").fetchone()
        if row is None or int(row[0]) != SCHEMA_VERSION:
            raise HTTPException(status_code=422, detail="Backup schema version does not match this application")
    except sqlite3.DatabaseError as exc:
        raise HTTPException(status_code=422, detail="Not a valid SQLite database") from exc
    finally:
        con.close()


def restore_backup(settings: Settings, engine: Engine, session: Session, data: bytes) -> dict:
    if not data.startswith(b"SQLite format 3\x00"):
        raise HTTPException(status_code=422, detail="Not a SQLite database file")
    if _jobs_running(session):
        raise HTTPException(status_code=409, detail="Wait for running solver jobs to finish first")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=settings.data_dir, suffix=".restore", delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        _check_backup_file(tmp_path)
        safety = create_backup(settings, "pre-restore")
        session.close()
        engine.dispose()
        src = sqlite3.connect(tmp_path)
        dst = sqlite3.connect(settings.database_path)
        try:
            src.backup(dst)  # overwrite the live database in place (works while files are open on Windows)
        finally:
            dst.close()
            src.close()
    finally:
        tmp_path.unlink(missing_ok=True)
    return {"restored": True, "safety_backup": safety.name}


def delete_all_data(settings: Settings, engine: Engine, session: Session, confirm: str) -> dict:
    if confirm != DELETE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"Type exactly: {DELETE_CONFIRMATION}")
    if _jobs_running(session):
        raise HTTPException(status_code=409, detail="Wait for running solver jobs to finish first")
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    seed_reference_data(session)
    session.commit()
    session.close()
    removed = 0
    if settings.backup_dir.is_dir():
        for p in settings.backup_dir.glob("shiftorbit-*.db"):
            p.unlink()
            removed += 1
    with engine.connect() as conn:  # rewrite the file so deleted rows do not linger in free pages
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.exec_driver_sql("VACUUM")
    return {"deleted": True, "backups_removed": removed}
