"""Background execution of solver runs.

Runs execute on a small thread pool so API requests stay responsive. Each run has a
``JobHandle`` that carries its cancellation flag and the live progress reported by the
solver callback (solutions found, objective, bound, elapsed time). Nothing here invents
progress: if the solver has not reported anything yet, progress stays empty.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from ..models import SolverRun, utcnow

log = logging.getLogger("shiftorbit.jobs")


class JobHandle:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._stoppers: list[Callable[[], None]] = []
        self._progress: dict[str, Any] = {}
        self.started_monotonic: float | None = None

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            stoppers = list(self._stoppers)
        for stop in stoppers:
            try:
                stop()
            except Exception:  # pragma: no cover - defensive
                log.exception("Failed to stop solver for run %s", self.run_id)

    def add_stopper(self, stop: Callable[[], None]) -> None:
        with self._lock:
            self._stoppers.append(stop)
        if self.cancelled:
            stop()

    def remove_stopper(self, stop: Callable[[], None]) -> None:
        with self._lock:
            if stop in self._stoppers:
                self._stoppers.remove(stop)

    def report(self, **values: Any) -> None:
        with self._lock:
            self._progress.update(values)

    def progress(self) -> dict[str, Any]:
        with self._lock:
            data = dict(self._progress)
        if self.started_monotonic is not None:
            data.setdefault("elapsed_seconds", round(time.monotonic() - self.started_monotonic, 2))
        return data


class JobManager:
    def __init__(self, session_factory: sessionmaker[Session], workers: int = 1) -> None:
        self._factory = session_factory
        self._executor = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="solver")
        self._handles: dict[str, JobHandle] = {}
        self._lock = threading.Lock()
        self._mark_interrupted_runs()

    def _mark_interrupted_runs(self) -> None:
        with self._factory() as session:
            session.execute(
                update(SolverRun)
                .where(SolverRun.state.in_(("queued", "running")))
                .values(state="failed", message="Interrupted: the application stopped during this run.")
            )
            session.commit()

    def submit(self, run_id: str, func: Callable[[JobHandle], None]) -> JobHandle:
        handle = JobHandle(run_id)
        with self._lock:
            self._handles[run_id] = handle

        def runner() -> None:
            handle.started_monotonic = time.monotonic()
            with self._factory() as session:
                run = session.get(SolverRun, run_id)
                if run is None:
                    return
                if handle.cancelled:
                    run.state = "cancelled"
                    run.finished_at = utcnow()
                    run.message = "Cancelled before start"
                    session.commit()
                    return
                run.state = "running"
                run.started_at = utcnow()
                session.commit()
            try:
                func(handle)
            except Exception as exc:
                log.exception("Solver run %s failed", run_id)
                with self._factory() as session:
                    run = session.get(SolverRun, run_id)
                    if run is not None:
                        run.state = "failed"
                        run.solver_status = run.solver_status or "ERROR"
                        run.message = f"Internal error: {type(exc).__name__}"
                        run.finished_at = utcnow()
                        session.commit()
            finally:
                handle.report(finished=True)

        self._executor.submit(runner)
        return handle

    def get(self, run_id: str) -> JobHandle | None:
        with self._lock:
            return self._handles.get(run_id)

    def cancel(self, run_id: str) -> bool:
        handle = self.get(run_id)
        if handle is None:
            return False
        handle.cancel()
        return True

    def shutdown(self) -> None:
        with self._lock:
            handles = list(self._handles.values())
        for h in handles:
            h.cancel()
        self._executor.shutdown(wait=True, cancel_futures=True)
