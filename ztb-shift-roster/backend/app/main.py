"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from .config import APP_NAME, APP_VERSION, Settings, load_settings
from .db import init_db, make_engine, make_session_factory
from .security import LocalSecurityMiddleware

log = logging.getLogger("shiftorbit")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_path)
    init_db(engine)

    from .services.jobs import JobManager

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        app.state.jobs.shutdown()
        app.state.engine.dispose()

    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = make_session_factory(engine)
    app.state.jobs = JobManager(app.state.session_factory, workers=settings.solver_workers)

    # Middleware order: the last added runs first. Security checks run before CORS handling.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-ztb-request"],
        max_age=600,
    )
    app.add_middleware(
        LocalSecurityMiddleware,
        allowed_hosts=settings.allowed_hosts,
        allowed_origins=settings.allowed_origins,
        max_body_bytes=settings.max_upload_bytes + 64 * 1024,
    )

    @app.exception_handler(IntegrityError)
    async def _integrity_error(_request: Request, _exc: IntegrityError):
        # Do not echo SQL or row values back to the client or the log.
        log.warning("Integrity constraint violation")
        return JSONResponse(
            status_code=409,
            content={"detail": "The change conflicts with existing data (duplicate or referenced record)."},
        )

    from .api import router as api_router

    app.include_router(api_router, prefix="/api")
    _mount_frontend(app, settings.frontend_dist)
    return app


def _mount_frontend(app: FastAPI, dist: Path | None) -> None:
    if dist is None or not (dist / "index.html").is_file():
        return
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")
    index = dist / "index.html"
    dist_resolved = dist.resolve()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith("api/"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and dist_resolved in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)
