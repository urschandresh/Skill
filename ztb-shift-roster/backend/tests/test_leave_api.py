from __future__ import annotations

from datetime import date

from .api_helpers import generate, setup_team, wait_job


def test_leave_lifecycle_and_validation(client):
    _p, analysts = setup_team(client, n=2)
    aid = analysts[0]["id"]
    r = client.post("/api/leaves", json={"analyst_id": aid, "start_date": "2026-11-10", "end_date": "2026-11-12",
                                         "reason": "Synthetic"})
    assert r.status_code == 201 and r.json()["status"] == "pending"
    leave = r.json()
    assert client.post("/api/leaves", json={"analyst_id": aid, "start_date": "2026-11-11",
                                            "end_date": "2026-11-13"}).status_code == 409
    bad = [
        {"analyst_id": aid, "start_date": "2026-11-12", "end_date": "2026-11-10"},
        {"analyst_id": aid, "start_date": "2026-11-12", "end_date": "2026-11-13", "partial_day": True,
         "start_time": "09:00", "end_time": "12:00"},
        {"analyst_id": aid, "start_date": "2026-11-12", "end_date": "2026-11-12", "partial_day": True},
        {"analyst_id": aid, "start_date": "2026-11-12", "end_date": "2026-11-12", "start_time": "09:00"},
        {"analyst_id": 9999, "start_date": "2026-11-12", "end_date": "2026-11-12"},
    ]
    for body in bad:
        assert client.post("/api/leaves", json=body).status_code in (404, 422), body

    r = client.put(f"/api/leaves/{leave['id']}", json={"analyst_id": aid, "start_date": "2026-11-10",
                                                       "end_date": "2026-11-11"})
    assert r.json()["end_date"] == "2026-11-11"
    assert client.post(f"/api/leaves/{leave['id']}/approve", json={"note": "ok"}).json()["status"] == "approved"
    assert client.post(f"/api/leaves/{leave['id']}/approve", json={}).status_code == 409
    # Editing an approved leave sends it back for approval.
    r = client.put(f"/api/leaves/{leave['id']}", json={"analyst_id": aid, "start_date": "2026-11-10",
                                                       "end_date": "2026-11-12"})
    assert r.json()["status"] == "pending"
    assert client.post(f"/api/leaves/{leave['id']}/reject", json={"note": "no"}).json()["status"] == "rejected"
    assert client.post(f"/api/leaves/{leave['id']}/cancel", json={}).status_code == 409

    r = client.post("/api/leaves", json={"analyst_id": aid, "start_date": "2026-11-20", "end_date": "2026-11-20",
                                         "partial_day": True, "start_time": "09:00", "end_time": "13:00"})
    assert r.status_code == 201
    assert client.post(f"/api/leaves/{r.json()['id']}/cancel", json={}).json()["status"] == "cancelled"
    assert len(client.get(f"/api/leaves?analyst_id={aid}&start=2026-11-01&end=2026-11-30").json()) == 2


def test_pending_leave_impact_replacements_and_regeneration(client):
    p, analysts = setup_team(client)
    job = generate(client, [p["id"]])
    rid = job["roster_id"]
    client.post(f"/api/rosters/{rid}/publish", json={})
    roster = client.get(f"/api/rosters/{rid}").json()
    victim = roster["assignments"][10]
    aid, day = victim["analyst_id"], victim["date"]
    leave = client.post("/api/leaves", json={"analyst_id": aid, "start_date": day, "end_date": day}).json()

    imp = client.get(f"/api/leaves/{leave['id']}/impact").json()
    assert imp["evaluated_as"].startswith("approved (simulation")
    entry = imp["rosters"][0]
    assert entry["roster_id"] == rid
    assert [a["date"] for a in entry["affected_assignments"]] == [day]
    assert any(v["rule"] == "absence" for v in entry["conflicts_if_kept"])
    # Simulation changed nothing.
    assert client.get(f"/api/rosters/{rid}").json()["assignment_count"] == roster["assignment_count"]

    rep = client.get(f"/api/leaves/{leave['id']}/replacements").json()
    assert rep["shifts"] and rep["shifts"][0]["date"] == day
    assert all(c["analyst_id"] != aid for c in rep["shifts"][0]["candidates"])

    # Simulate regeneration while still pending: no new roster is saved.
    r = client.post(f"/api/leaves/{leave['id']}/regenerate", json={"roster_id": rid, "simulate": True,
                                                                   "time_limit_seconds": 20})
    assert r.status_code == 202
    sim = wait_job(client, r.json()["run_id"])
    assert sim["state"] == "completed" and sim["roster_id"] is None, sim
    assert sim["result"]["validation"]["is_valid"]
    assert sim["result"]["changes"]["removed"] >= 1
    assert len(client.get("/api/rosters?year=2026&month=11").json()) == 1

    # Real regeneration requires approval.
    assert client.post(f"/api/leaves/{leave['id']}/regenerate", json={"roster_id": rid}).status_code == 409
    client.post(f"/api/leaves/{leave['id']}/approve", json={})
    imp = client.get(f"/api/leaves/{leave['id']}/impact").json()
    assert any(v["rule"] == "absence" for v in imp["rosters"][0]["conflicts_if_kept"])
    val = client.get(f"/api/rosters/{rid}/validation").json()
    assert not val["is_valid"] and val["by_rule"].get("absence") == 1

    r = client.post(f"/api/leaves/{leave['id']}/regenerate", json={"roster_id": rid, "margin_days": 2,
                                                                   "time_limit_seconds": 20})
    job = wait_job(client, r.json()["run_id"])
    assert job["state"] == "completed" and job["roster_id"], job
    new = client.get(f"/api/rosters/{job['roster_id']}").json()
    assert new["status"] == "draft" and new["parent_roster_id"] == rid
    assert not [a for a in new["assignments"] if a["analyst_id"] == aid and a["date"] == day]
    assert client.get(f"/api/rosters/{job['roster_id']}/validation").json()["is_valid"]
    # Outside the window nothing moved.
    lo, hi = r.json()["window_start"], r.json()["window_end"]
    key = lambda a: (a["analyst_id"], a["shift_template_id"], a["date"])  # noqa: E731
    old_out = {key(a) for a in roster["assignments"] if not lo <= a["date"] <= hi}
    new_out = {key(a) for a in new["assignments"] if not lo <= a["date"] <= hi}
    assert old_out == new_out
    cell = next(r for r in new["rows"] if r["analyst_id"] == aid)["cells"][day]
    assert cell["marker"] == "LEAVE"
