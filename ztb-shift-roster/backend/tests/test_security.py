from __future__ import annotations

from fastapi.testclient import TestClient

from .conftest import BASE_URL


def test_state_change_without_csrf_header_rejected(raw_client):
    r = raw_client.post("/api/health")
    assert r.status_code == 403
    assert "X-ZTB-Request" in r.json()["detail"]


def test_foreign_origin_rejected(client):
    r = client.post("/api/health", headers={"Origin": "http://evil.example"})
    assert r.status_code == 403


def test_cross_site_fetch_metadata_rejected(client):
    r = client.post("/api/health", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403


def test_allowed_origin_passes_security_layer(client):
    # 405 (method not allowed) proves the request got past the security middleware.
    r = client.post("/api/health", headers={"Origin": BASE_URL})
    assert r.status_code == 405


def test_dns_rebinding_host_rejected(app):
    with TestClient(app, base_url="http://attacker.example:8000") as c:
        r = c.get("/api/health")
    assert r.status_code == 400


def test_ipv6_loopback_host_allowed(app):
    with TestClient(app, base_url="http://[::1]:8000") as c:
        assert c.get("/api/health").status_code == 200


def test_cors_preflight_only_for_local_origin(client):
    ok = client.options(
        "/api/health",
        headers={"Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "x-ztb-request"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"
    bad = client.options(
        "/api/health",
        headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "x-ztb-request"},
    )
    assert bad.headers.get("access-control-allow-origin") is None


def test_oversized_body_rejected(client, settings):
    big = b"x" * (settings.max_upload_bytes + 200 * 1024)
    r = client.post("/api/health", content=big, headers={"Content-Type": "application/octet-stream"})
    assert r.status_code == 413
