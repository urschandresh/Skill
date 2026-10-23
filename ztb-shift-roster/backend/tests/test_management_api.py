from __future__ import annotations


def make_project(client, code="SOC1", **kw):
    r = client.post("/api/projects", json={"code": code, "name": f"Project {code}", **kw})
    assert r.status_code == 201, r.text
    return r.json()


def test_project_crud_with_default_shifts(client):
    p = make_project(client, description="Synthetic test project")
    assert [t["code"] for t in p["shift_templates"]] == ["M", "A", "N"]
    night = next(t for t in p["shift_templates"] if t["code"] == "N")
    assert night["overnight"] is True and night["duration_minutes"] == 540 and night["is_night"]
    assert len(p["staffing"]) == 3 and all(s["min_staff"] == 1 for s in p["staffing"])

    r = client.put(f"/api/projects/{p['id']}", json={"code": "soc1", "name": "Renamed", "timezone": "Asia/Kolkata"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed" and r.json()["code"] == "SOC1"
    assert client.get("/api/projects").json()[0]["id"] == p["id"]
    assert client.delete(f"/api/projects/{p['id']}").status_code == 204
    assert client.get(f"/api/projects/{p['id']}").status_code == 404


def test_duplicate_project_code_conflict(client):
    make_project(client)
    r = client.post("/api/projects", json={"code": "SOC1", "name": "Dup"})
    assert r.status_code == 409
    assert "SOC1" not in r.text  # no data echoed from the DB layer


def test_invalid_project_inputs(client):
    assert client.post("/api/projects", json={"code": "", "name": "x"}).status_code == 422
    assert client.post("/api/projects", json={"code": "OK", "name": "x", "timezone": "Mars/Base"}).status_code == 422
    assert client.post("/api/projects", json={"code": "OK", "name": "x", "unknown": 1}).status_code == 422
    assert client.post("/api/projects", json={"code": "OK", "name": "bad\x00name"}).status_code == 422
    assert client.post("/api/projects", json={"code": "=cmd()", "name": "x"}).status_code == 422


def test_shift_template_validation_and_overlap_allowed(client):
    p = make_project(client, create_default_shifts=False)
    base = f"/api/projects/{p['id']}/shift-templates"
    r = client.post(base, json={"code": "D", "name": "Day", "start_time": "09:00", "end_time": "18:00"})
    assert r.status_code == 201 and r.json()["duration_minutes"] == 540
    # Overlapping templates are allowed (D overlaps a 06-15 morning).
    r = client.post(base, json={"code": "M", "name": "Morning", "start_time": "06:00", "end_time": "15:00"})
    assert r.status_code == 201
    assert client.post(base, json={"code": "WO", "name": "x", "start_time": "06:00", "end_time": "15:00"}).status_code == 422
    assert client.post(base, json={"code": "X", "name": "x", "start_time": "25:00", "end_time": "15:00"}).status_code == 422
    assert client.post(base, json={"code": "Y", "name": "x", "start_time": "06:00", "end_time": "06:30"}).status_code == 422
    assert client.post(base, json={"code": "D", "name": "dup", "start_time": "06:00", "end_time": "15:00"}).status_code == 409


def test_staffing_requirements(client):
    p = make_project(client)
    tpl = p["shift_templates"][0]["id"]
    base = f"/api/projects/{p['id']}/staffing"
    r = client.post(base, json={"shift_template_id": tpl, "weekday": 5, "min_staff": 2, "max_staff": 3})
    assert r.status_code == 201
    assert client.post(base, json={"shift_template_id": tpl, "weekday": 5, "min_staff": 1}).status_code == 409
    assert client.post(base, json={"shift_template_id": tpl, "min_staff": 3, "max_staff": 1}).status_code == 422
    other = make_project(client, code="SOC2")
    assert client.post(base, json={"shift_template_id": other["shift_templates"][0]["id"]}).status_code == 422
    assert len(client.get(base).json()) == 4


def test_analyst_crud_skills_eligibility(client):
    p1, p2 = make_project(client), make_project(client, code="SOC2")
    skill = client.post("/api/skills", json={"name": "SIEM"}).json()
    body = {
        "employee_code": "SYN-001",
        "full_name": "Synthetic Analyst One",
        "skill_ids": [skill["id"]],
        "preferences": {"preferred_shifts": ["m"], "avoid_shifts": ["N"], "preferred_off_days": [5, 6]},
        "eligibility": [
            {"project_id": p1["id"], "is_primary": True},
            {"project_id": p2["id"], "allowed_shift_codes": ["M", "A"]},
        ],
    }
    r = client.post("/api/analysts", json=body)
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["skill_ids"] == [skill["id"]]
    assert a["preferences"]["preferred_shifts"] == ["M"]
    assert {e["project_id"] for e in a["eligibility"]} == {p1["id"], p2["id"]}

    r = client.put(f"/api/analysts/{a['id']}/eligibility", json=[{"project_id": p2["id"]}])
    assert [e["project_id"] for e in r.json()["eligibility"]] == [p2["id"]]
    assert len(client.get(f"/api/analysts?project_id={p2['id']}").json()) == 1
    assert len(client.get(f"/api/analysts?project_id={p1['id']}").json()) == 0

    bad = dict(body, eligibility=[{"project_id": 9999}], employee_code="SYN-002")
    assert client.post("/api/analysts", json=bad).status_code == 422
    assert client.post("/api/analysts", json=dict(body, skill_ids=[9999], employee_code="SYN-003")).status_code == 422
    assert client.post("/api/analysts", json=dict(body, email="not-an-email", employee_code="SYN-004")).status_code == 422
    assert client.post("/api/analysts", json=body).status_code == 409  # duplicate employee code
    assert client.delete(f"/api/analysts/{a['id']}").status_code == 204


def test_policy_crud_and_single_default(client):
    policies = client.get("/api/policies").json()
    assert len(policies) == 1 and policies[0]["is_default"]
    r = client.post("/api/policies", json={"name": "Strict", "is_default": True, "max_consecutive_nights": 3,
                                           "weights": {"fair_nights": 50}})
    assert r.status_code == 201
    new = r.json()
    assert new["weights"]["fair_nights"] == 50 and new["weights"]["disruption"] == 20
    policies = client.get("/api/policies").json()
    assert [p["name"] for p in policies if p["is_default"]] == ["Strict"]
    assert client.delete(f"/api/policies/{new['id']}").status_code == 409
    assert client.post("/api/policies", json={"name": "Bad", "min_rest_hours": 30}).status_code == 422
    assert client.post("/api/policies", json={"name": "Bad", "weekly_mode": "sometimes"}).status_code == 422


def test_availability_holidays_mappings(client):
    a = client.post("/api/analysts", json={"employee_code": "SYN-9", "full_name": "Synthetic Nine"}).json()
    r = client.post("/api/availability", json={"analyst_id": a["id"], "date": "2026-11-03", "kind": "block_shifts",
                                               "shift_codes": ["N"]})
    assert r.status_code == 201
    assert client.post("/api/availability", json={"analyst_id": a["id"], "date": "2026-11-03",
                                                   "kind": "block_shifts"}).status_code == 422
    assert len(client.get(f"/api/availability?analyst_id={a['id']}").json()) == 1

    r = client.post("/api/holidays", json={"date": "2026-11-08", "name": "Synthetic holiday"})
    assert r.status_code == 201
    assert len(client.get("/api/holidays?year=2026").json()) == 1

    r = client.post("/api/shift-code-mappings", json={"source_code": "g", "target_kind": "shift",
                                                      "target_shift_code": "D"})
    assert r.status_code == 201 and r.json()["source_code"] == "G"
    assert client.post("/api/shift-code-mappings", json={"source_code": "Z", "target_kind": "shift"}).status_code == 422
