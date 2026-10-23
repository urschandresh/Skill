from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

BASE_URL = "http://127.0.0.1:8000"
WRITE_HEADERS = {"X-ZTB-Request": "1", "Origin": BASE_URL}


@pytest.fixture()
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "data", frontend_dist=None)


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    with TestClient(app, base_url=BASE_URL, headers={"X-ZTB-Request": "1"}) as c:
        yield c


@pytest.fixture()
def raw_client(app):
    """A client that sends no CSRF header, to test the protections."""
    with TestClient(app, base_url=BASE_URL) as c:
        yield c
