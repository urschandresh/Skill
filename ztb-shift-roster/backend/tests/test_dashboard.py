from .api_helpers import generate, setup_team


def test_dashboard_empty_and_populated(client):
    d = client.get("/api/dashboard?year=2026&month=11").json()
    assert d["totals"]["projects"] == 0 and d["coverage_percent"] is None and d["rosters"] == []
    p, analysts = setup_team(client)
    client.post("/api/leaves", json={"analyst_id": analysts[0]["id"], "start_date": "2026-11-20",
                                     "end_date": "2026-11-20"})
    job = generate(client, [p["id"]])
    d = client.get("/api/dashboard?year=2026&month=11").json()
    assert d["totals"] == {"projects": 1, "active_analysts": 7, "pending_leaves": 1, "approved_leaves_this_month": 0}
    assert d["coverage_percent"] == 100.0
    assert d["rosters"][0]["id"] == job["roster_id"] and d["rosters"][0]["is_valid"]
    assert sum(x["count"] for x in d["shift_distribution"]) == d["rosters"][0]["assignment_count"]
    assert len(d["workload"]) == 7 and all(w["hours"] > 0 for w in d["workload"])
    assert d["recent_runs"][0]["state"] == "completed"
