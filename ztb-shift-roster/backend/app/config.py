"""Runtime settings, read from environment variables with local-safe defaults."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DATA_DIR = PROJECT_DIR / "data"
DEFAULT_FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

APP_NAME = "ZTB ShiftOrbit"
APP_VERSION = "0.1.0"
SCHEMA_VERSION = 1


def _is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Settings:
    data_dir: Path = DEFAULT_DATA_DIR
    db_path: Path | None = None
    host: str = "127.0.0.1"
    port: int = 8000
    allowed_origins: tuple[str, ...] = (
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    )
    max_upload_bytes: int = 5 * 1024 * 1024
    max_solver_seconds: int = 600
    solver_workers: int = 1
    frontend_dist: Path | None = DEFAULT_FRONTEND_DIST
    log_level: str = "INFO"
    # The interactive API docs page loads its assets from a public CDN, so it is off by default.
    enable_api_docs: bool = False
    allowed_hosts: tuple[str, ...] = field(default=("127.0.0.1", "localhost"))

    @property
    def database_path(self) -> Path:
        return self.db_path or (self.data_dir / "shiftorbit.db")

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    def validate(self) -> None:
        if not _is_loopback(self.host) and os.environ.get("ZTB_ALLOW_NON_LOOPBACK") != "1":
            raise ValueError(
                f"Refusing to bind to non-loopback host {self.host!r}. ShiftOrbit is local-only; "
                "set ZTB_ALLOW_NON_LOOPBACK=1 only if you understand there is no user authentication."
            )
        if not (1 <= self.port <= 65535):
            raise ValueError("Port must be between 1 and 65535")


def load_settings() -> Settings:
    env = os.environ
    data_dir = Path(env.get("ZTB_DATA_DIR", str(DEFAULT_DATA_DIR)))
    db_path = Path(env["ZTB_DB_PATH"]) if env.get("ZTB_DB_PATH") else None
    port = int(env.get("ZTB_PORT", "8000"))
    origins_env = env.get("ZTB_ALLOWED_ORIGINS")
    origins = (
        tuple(o.strip().rstrip("/") for o in origins_env.split(",") if o.strip())
        if origins_env
        else (
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        )
    )
    dist = env.get("ZTB_FRONTEND_DIST")
    settings = Settings(
        data_dir=data_dir,
        db_path=db_path,
        host=env.get("ZTB_HOST", "127.0.0.1"),
        port=port,
        allowed_origins=origins,
        max_upload_bytes=int(env.get("ZTB_MAX_UPLOAD_MB", "5")) * 1024 * 1024,
        max_solver_seconds=int(env.get("ZTB_MAX_SOLVER_SECONDS", "600")),
        frontend_dist=Path(dist) if dist else DEFAULT_FRONTEND_DIST,
        log_level=env.get("ZTB_LOG_LEVEL", "INFO").upper(),
        enable_api_docs=env.get("ZTB_ENABLE_API_DOCS") == "1",
    )
    settings.validate()
    return settings
