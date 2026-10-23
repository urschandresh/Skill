"""Helpers that create SYNTHETIC data through the public API."""

from __future__ import annotations

import time


def setup_team(client, n=7, code="SYN", min_staff=1):
    p = client.post("/api/projects", json={"code": code, "name": f"Synthetic {code}",
                                           "default_min_staff": min_staff}).json()
    analysts = []
    for i in range(n):
        r = client.post("/api/analysts", json={
            "employee_code": f"{code}-{i + 1:03d}", "full_name": f"Synthetic Analyst {code} {i + 1}",
            "eligibility": [{"project_id": p["id"], "is_primary": True}]})
        assert r.status_code == 201, r.text
        analysts.append(r.json())
    return p, analysts


def wait_job(client, run_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{run_id}").json()
        if job["state"] not in ("queued", "running"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def generate(client, project_ids, year=2026, month=11, **extra):
    r = client.post("/api/rosters/generate", json={"year": year, "month": month, "project_ids": project_ids,
                                                   "time_limit_seconds": 20, **extra})
    assert r.status_code == 202, r.text
    return wait_job(client, r.json()["run_id"])
