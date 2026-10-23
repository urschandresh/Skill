from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import select

from app.config import Settings
from app.db import SchemaVersionError, init_db, make_engine
from app.models import AppMeta, SchedulingPolicy, ShiftCodeMapping


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "CP-SAT" in body["solver"]


def test_security_headers_present(client):
    r = client.get("/api/health")
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_reference_data_seeded(app):
    with app.state.session_factory() as s:
        assert s.scalar(select(SchedulingPolicy).where(SchedulingPolicy.is_default)) is not None
        codes = set(s.scalars(select(ShiftCodeMapping.source_code)))
        assert {"M", "A", "N", "D", "AN", "WO", "LEAVE", "H"} <= codes


def test_database_file_persists_between_app_instances(settings):
    from app.main import create_app

    create_app(settings)
    assert settings.database_path.exists()
    con = sqlite3.connect(settings.database_path)
    tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
    con.close()
    assert {"projects", "analysts", "assignments", "rosters", "leave_requests"} <= tables


def test_schema_version_mismatch_refuses_start(tmp_path):
    engine = make_engine(tmp_path / "x.db")
    init_db(engine)
    from app.db import make_session_factory

    with make_session_factory(engine)() as s:
        s.get(AppMeta, "schema_version").value = "999"
        s.commit()
    with pytest.raises(SchemaVersionError):
        init_db(engine)


def test_non_loopback_host_refused(monkeypatch):
    monkeypatch.delenv("ZTB_ALLOW_NON_LOOPBACK", raising=False)
    with pytest.raises(ValueError):
        Settings(host="0.0.0.0").validate()
    Settings(host="127.0.0.1").validate()
    Settings(host="::1").validate()
