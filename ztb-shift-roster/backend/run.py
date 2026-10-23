"""Start ShiftOrbit on the loopback interface: ``python run.py``."""

from __future__ import annotations

import logging

import uvicorn

from app.config import load_settings
from app.main import create_app


def main() -> None:
    settings = load_settings()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app(settings)
    print(f"ZTB ShiftOrbit running at http://{settings.host}:{settings.port}  (Ctrl+C to stop)")
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level.lower(),
                proxy_headers=False, server_header=False)


if __name__ == "__main__":
    main()
