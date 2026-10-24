"""Route-wide protections, injection handling and log hygiene."""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from .api_helpers import generate, setup_team
from .conftest import BASE_URL


def _write_routes(app):
    import re

    for path, ops in app.openapi()["paths"].items():
        for method in ops:
            if method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
                yield method.upper(), re.sub(r"\{[^}]+\}", "1", path)


def test_every_state_changing_route_requires_csrf_header(app):
    routes = list(_write_routes(app))
    assert len(routes) > 35, len(routes)
    with TestClient(app, base_url=BASE_URL) as c:
        for method, path in routes:
            r = c.request(method, path, json={})
            assert r.status_code == 403, (method, path, r.status_code)
            r = c.request(method, path, json={}, headers={"X-ZTB-Request": "1", "Origin": "http://evil.example"})
            assert r.status_code == 403, (method, path)


def test_sql_metacharacters_stored_literally(client):
    evil = "Robert'); DROP TABLE analysts;--"
    r = client.post("/api/analysts", json={"employee_code": "SYN-1", "full_name": evil})
    assert r.status_code == 201
    assert client.get("/api/analysts").json()[0]["full_name"] == evil
    assert client.get("/api/projects?include_inactive=1' OR '1'='1").status_code == 422


def test_spa_static_path_traversal(tmp_path):
    from app.config import Settings
    from app.main import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>app</html>")
    (tmp_path / "secret.txt").write_text("top secret")
    app = create_app(Settings(data_dir=tmp_path / "data", frontend_dist=dist))
    with TestClient(app, base_url=BASE_URL) as c:
        for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt", "/..%2fsecret.txt"):
            r = c.get(path)
            assert "top secret" not in r.text, path
        assert c.get("/rosters/5").text == "<html>app</html>"
        assert c.get("/api/nope").status_code == 404


def test_api_docs_disabled_by_default(client):
    assert client.get("/api/docs").status_code in (404, 200) and "swagger" not in client.get("/api/docs").text.lower()
    assert client.get("/api/openapi.json").status_code == 200


def test_logs_do_not_contain_staff_names(client, caplog):
    caplog.set_level(logging.DEBUG)
    p, analysts = setup_team(client)
    client.post("/api/analysts", json={"employee_code": analysts[0]["employee_code"], "full_name": "Duplicate Person"})
    generate(client, [p["id"]])
    text = caplog.text
    assert "Synthetic Analyst" not in text and "Duplicate Person" not in text


def test_internal_errors_do_not_leak_details(app):
    @app.get("/api/boom")
    def boom():
        raise RuntimeError("secret detail /home/user/data.db")

    with TestClient(app, base_url=BASE_URL, raise_server_exceptions=False) as c:
        r = c.get("/api/boom")
    assert r.status_code == 500 and "secret detail" not in r.text
