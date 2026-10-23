from __future__ import annotations

import sqlite3

from .api_helpers import generate, setup_team


def test_backup_restore_roundtrip(client, settings):
    p, _ = setup_team(client)
    r = client.post("/api/admin/backups")
    assert r.status_code == 201
    name = r.json()["name"]
    assert [b["name"] for b in client.get("/api/admin/backups").json()] == [name]
    dl = client.get(f"/api/admin/backups/{name}")
    assert dl.status_code == 200 and dl.content.startswith(b"SQLite format 3\x00")

    # Change data after the backup, then restore: the change must disappear.
    client.post("/api/projects", json={"code": "LATER", "name": "Added after backup"})
    assert len(client.get("/api/projects").json()) == 2
    r = client.post("/api/admin/restore", files={"file": ("b.db", dl.content, "application/octet-stream")})
    assert r.status_code == 200, r.text
    assert "pre-restore" in r.json()["safety_backup"]
    assert [x["code"] for x in client.get("/api/projects").json()] == ["SYN"]


def test_restore_rejects_bad_files(client, tmp_path):
    r = client.post("/api/admin/restore", files={"file": ("x.db", b"not a database", "application/octet-stream")})
    assert r.status_code == 422
    other = tmp_path / "other.db"
    con = sqlite3.connect(other)
    con.execute("create table t(x)")
    con.commit()
    con.close()
    r = client.post("/api/admin/restore", files={"file": ("o.db", other.read_bytes(), "application/octet-stream")})
    assert r.status_code == 422 and "ShiftOrbit" in r.text


def test_backup_download_path_traversal_blocked(client):
    assert client.get("/api/admin/backups/..%2F..%2Fshiftorbit.db").status_code in (400, 404)
    assert client.get("/api/admin/backups/shiftorbit-20260101-000000.db").status_code == 404


def test_delete_all_data(client, settings):
    p, _ = setup_team(client)
    generate(client, [p["id"]])
    client.post("/api/admin/backups")
    assert client.post("/api/admin/delete-all-data", json={"confirm": "yes"}).status_code == 422
    r = client.post("/api/admin/delete-all-data", json={"confirm": "DELETE ALL DATA"})
    assert r.status_code == 200 and r.json()["backups_removed"] == 1
    assert client.get("/api/projects").json() == []
    assert client.get("/api/analysts").json() == []
    assert client.get("/api/rosters").json() == []
    assert len(client.get("/api/policies").json()) == 1  # reference data re-seeded
    con = sqlite3.connect(settings.database_path)
    assert con.execute("select count(*) from analysts").fetchone()[0] == 0
    con.close()
    raw = settings.database_path.read_bytes()
    assert b"Synthetic Analyst" not in raw  # VACUUM removed the deleted rows from the file


def test_demo_data_only_on_empty_db(client):
    r = client.post("/api/admin/demo-data")
    assert r.status_code == 201 and r.json()["analysts"] == 12
    assert client.post("/api/admin/demo-data").status_code == 409
    analysts = client.get("/api/analysts").json()
    assert all(a["employee_code"].startswith("SYN-") for a in analysts)
    audit = client.get("/api/admin/audit").json()
    assert audit[0]["action"] == "load_demo"
