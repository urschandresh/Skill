"""SQLite engine, session factory and schema bootstrap."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import SCHEMA_VERSION


class Base(DeclarativeBase):
    pass


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - exercised implicitly
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


class SchemaVersionError(RuntimeError):
    pass


def init_db(engine: Engine) -> None:
    """Create tables, check the schema version and seed reference data."""
    from . import models  # noqa: F401  (registers mappers)
    from .models import AppMeta
    from .services.seed import seed_reference_data

    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)
    with factory() as session:
        meta = session.scalar(select(AppMeta).where(AppMeta.key == "schema_version"))
        if meta is None:
            session.add(AppMeta(key="schema_version", value=str(SCHEMA_VERSION)))
            session.commit()
        elif int(meta.value) != SCHEMA_VERSION:
            raise SchemaVersionError(
                f"Database schema version {meta.value} does not match application version "
                f"{SCHEMA_VERSION}. Restore a matching backup or export your data first."
            )
        seed_reference_data(session)
        session.commit()


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
