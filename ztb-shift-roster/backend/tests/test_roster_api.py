from __future__ import annotations

from .api_helpers import generate, setup_team, wait_job


def _slot(a):
    return {k: a[k] for k in ("analyst_id", "project_id", "shift_template_id", "date")}


def test_generate_validate_publish_flow(client):
    p, analysts = setup_team(client)
    pre = client.post("/api/rosters/feasibility", json={"year": 2026, "month": 11, "project_ids": [p["id"]]}).json()
    assert pre["ok"] and pre["summary"]["analysts"] == 7

    job = generate(client, [p["id"]])
    assert job["state"] == "completed", job
    assert job["solver_status"] in ("OPTIMAL", "FEASIBLE")
    assert job["result"]["validation"]["is_valid"]
    roster_id = job["roster_id"]

    detail = client.get(f"/api/rosters/{roster_id}").json()
    assert detail["status"] == "draft" and detail["version"] == 1
    assert len(detail["rows"]) == 7
    cells = detail["rows"][0]["cells"]
    assert len(cells) == 30
    assert {c["marker"] for c in cells.values()} <= {None, "WO"}

    val = client.get(f"/api/rosters/{roster_id}/validation").json()
    assert val["is_valid"] and val["coverage_percent"] == 100.0

    r = client.post(f"/api/rosters/{roster_id}/publish", json={})
    assert r.status_code == 200 and r.json()["status"] == "published"
    # Published rosters are read-only and kept.
    a0 = detail["assignments"][0]
    r = client.post(f"/api/rosters/{roster_id}/changes", json={"ops": [{"op": "remove", **_slot(a0)}]})
    assert r.status_code == 409
    assert client.delete(f"/api/rosters/{roster_id}").status_code == 409

    clone = client.post(f"/api/rosters/{roster_id}/clone").json()
    assert clone["status"] == "draft" and clone["version"] == 2 and clone["assignment_count"] == detail["assignment_count"]


def test_manual_edit_validation_and_override(client):
    p, _ = setup_team(client)
    job = generate(client, [p["id"]])
    rid = job["roster_id"]
    detail = client.get(f"/api/rosters/{rid}").json()
    # Removing the only person on a shift breaks coverage -> rejected without an override.
    target = next(a for a in detail["assignments"]
                  if sum(1 for b in detail["assignments"] if b["shift_template_id"] == a["shift_template_id"]
                         and b["date"] == a["date"]) == 1)
    op = {"op": "remove", **_slot(target)}
    dry = client.post(f"/api/rosters/{rid}/changes", json={"ops": [op], "dry_run": True}).json()
    assert dry["committed"] is False and any(v["rule"] == "coverage" for v in dry["introduced"])
    r = client.post(f"/api/rosters/{rid}/changes", json={"ops": [op]})
    assert r.status_code == 409
    assert client.get(f"/api/rosters/{rid}").json()["assignment_count"] == detail["assignment_count"]
    r = client.post(f"/api/rosters/{rid}/changes", json={"ops": [op], "override_reason": "Synthetic test override"})
    assert r.status_code == 200 and r.json()["committed"]
    assert r.json()["roster"]["assignment_count"] == detail["assignment_count"] - 1
    # Undo = inverse operation.
    r = client.post(f"/api/rosters/{rid}/changes", json={"ops": [{"op": "add", **_slot(target)}]})
    assert r.status_code == 200 and r.json()["resolved"]
    # Publishing with violations needs a reason: make one, then try.
    client.post(f"/api/rosters/{rid}/changes", json={"ops": [op], "override_reason": "Synthetic test override"})
    r = client.post(f"/api/rosters/{rid}/publish", json={})
    assert r.status_code == 409
    r = client.post(f"/api/rosters/{rid}/publish", json={"override_reason": "Accepted shortfall (synthetic)"})
    assert r.status_code == 200


def test_locks_survive_and_block_edits(client):
    p, _ = setup_team(client)
    rid = generate(client, [p["id"]])["roster_id"]
    a = client.get(f"/api/rosters/{rid}").json()["assignments"][3]
    assert client.post(f"/api/rosters/{rid}/changes", json={"ops": [{"op": "lock", **_slot(a)}]}).status_code == 200
    r = client.post(f"/api/rosters/{rid}/changes", json={"ops": [{"op": "remove", **_slot(a)}]})
    assert r.status_code == 409 and "locked" in r.text
    job = wait_job(client, client.post(f"/api/rosters/{rid}/regenerate", json={"time_limit_seconds": 20}).json()["run_id"])
    assert job["state"] == "completed", job
    new = client.get(f"/api/rosters/{job['roster_id']}").json()
    kept = [x for x in new["assignments"] if _slot(x) == _slot(a)]
    assert kept and kept[0]["locked"]
    assert new["parent_roster_id"] == rid and new["version"] == 2


def test_infeasible_request_reports_diagnostics(client):
    p, _ = setup_team(client, n=3)
    job = generate(client, [p["id"]])
    assert job["state"] == "completed"
    assert job["solver_status"] == "INFEASIBLE"
    assert job["roster_id"] is None
    assert job["result"]["diagnostics"]


def test_invalid_generation_input(client):
    p, _ = setup_team(client, n=2)
    bad = [
        {"year": 2026, "month": 13, "project_ids": [p["id"]]},
        {"year": 2026, "month": 11, "project_ids": []},
        {"year": 2026, "month": 11, "project_ids": [999]},
        {"year": 2026, "month": 11, "project_ids": [p["id"]], "time_limit_seconds": 0},
        {"year": 2026, "month": 11, "project_ids": [p["id"]], "policy_overrides": {"min_rest_hours": 99}},
        {"year": 2026, "month": 11, "project_ids": [p["id"]], "analyst_ids": [999]},
    ]
    for body in bad:
        assert client.post("/api/rosters/generate", json=body).status_code == 422, body


def test_month_boundary_uses_published_previous_roster(client):
    p, _ = setup_team(client)
    nov = generate(client, [p["id"]], month=11)
    client.post(f"/api/rosters/{nov['roster_id']}/publish", json={})
    dec = generate(client, [p["id"]], month=12)
    assert dec["state"] == "completed" and dec["solver_status"] in ("OPTIMAL", "FEASIBLE"), dec
    assert any("Continuity from previous month" in n for n in dec["result"]["notes"])
    nov_a = client.get(f"/api/rosters/{nov['roster_id']}").json()["assignments"]
    dec_a = client.get(f"/api/rosters/{dec['roster_id']}").json()["assignments"]
    tpl = {t["id"]: t["code"] for t in p["shift_templates"]}
    last = {a["analyst_id"]: tpl[a["shift_template_id"]] for a in nov_a if a["date"] == "2026-11-30"}
    first = {a["analyst_id"]: tpl[a["shift_template_id"]] for a in dec_a if a["date"] == "2026-12-01"}
    for aid, code in last.items():
        if code == "N":
            assert first.get(aid) not in ("M", "A")


def test_other_published_roster_prevents_cross_project_double_booking(client):
    p1, analysts = setup_team(client, code="PA")
    p2 = client.post("/api/projects", json={"code": "PB", "name": "Synthetic PB"}).json()
    # Analysts become eligible for both projects; PB is rostered separately afterwards.
    for a in analysts:
        client.put(f"/api/analysts/{a['id']}/eligibility",
                   json=[{"project_id": p1["id"], "is_primary": True}, {"project_id": p2["id"]}])
    extra = []
    for i in range(5):
        extra.append(client.post("/api/analysts", json={"employee_code": f"PB-{i}", "full_name": f"Synthetic PB {i}",
                                                         "eligibility": [{"project_id": p2["id"]}]}).json())
    first = generate(client, [p1["id"]], analyst_ids=[a["id"] for a in analysts])
    client.post(f"/api/rosters/{first['roster_id']}/publish", json={})
    second = generate(client, [p2["id"]], analyst_ids=[a["id"] for a in analysts + extra])
    assert second["solver_status"] in ("OPTIMAL", "FEASIBLE"), second
    assert any("kept fixed" in n for n in second["result"]["notes"])
    a1 = client.get(f"/api/rosters/{first['roster_id']}").json()["assignments"]
    a2 = client.get(f"/api/rosters/{second['roster_id']}").json()["assignments"]
    busy = {(a["analyst_id"], a["date"]) for a in a1}
    assert not [a for a in a2 if (a["analyst_id"], a["date"]) in busy]


def test_cancel_job(client):
    p, _ = setup_team(client, n=7)
    r = client.post("/api/rosters/generate", json={"year": 2026, "month": 11, "project_ids": [p["id"]],
                                                   "time_limit_seconds": 60})
    run_id = r.json()["run_id"]
    client.post(f"/api/jobs/{run_id}/cancel")
    job = wait_job(client, run_id)
    assert job["state"] in ("cancelled", "completed")
    assert client.post(f"/api/jobs/{run_id}/cancel").status_code == 409
