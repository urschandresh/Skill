from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from ..config import APP_NAME, APP_VERSION, SCHEMA_VERSION

router = APIRouter(tags=["health"])


@router.get("/health")
def health(request: Request) -> dict:
    with request.app.state.session_factory() as session:
        session.execute(text("SELECT 1"))
    import ortools

    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "solver": f"OR-Tools CP-SAT {ortools.__version__}",
        "timezone_default": "Asia/Kolkata",
    }
