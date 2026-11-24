"""Headless conveyor daemon lock, SIGTERM cleanup, and WAL checkpoint (Task 097)."""

from __future__ import annotations

import os
import signal
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

DEFAULT_BUSY_TIMEOUT_MS = 5000


class DaemonLockHeldError(Exception):
    """Another process already holds pipeline.db.lock."""


@dataclass
class DaemonShutdownState:
    lock_released: bool = False
    wal_checkpoint_requested: bool = False


@dataclass
class DaemonSession:
    db_path: Path
    lock_path: Path
    owner_id: str
    _advisory: "_AdvisoryPipelineLock"
    connection: sqlite3.Connection | None = None


class _AdvisoryPipelineLock:
    """Exclusive advisory lock on ``pipeline.db.lock`` (non-blocking second acquire)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None
        self.path.parent.mkdir(parents=True, exist_ok=True)
        flags = os.O_RDWR | os.O_CREAT
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        fd = os.open(os.fspath(path), flags, 0o600)
        try:
            fh = os.fdopen(fd, "r+b", closefd=True)
        except Exception:
            os.close(fd)
            raise
        try:
            self._ensure_lock_byte(fh)
            self._acquire(fh)
        except Exception:
            fh.close()
            raise
        self._fh = fh

    @staticmethod
    def _ensure_lock_byte(fh) -> None:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        fh.seek(0)

    def _acquire(self, fh) -> None:
        if os.name == "nt":
            import msvcrt

            try:
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DaemonLockHeldError(
                    f"sole-writer lock is already held: {self.path}"
                ) from exc
            return
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise DaemonLockHeldError(
                f"sole-writer lock is already held: {self.path}"
            ) from exc

    @property
    def held(self) -> bool:
        return self._fh is not None

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        self._fh = None
        try:
            if os.name == "nt":
                import msvcrt

                try:
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            fh.close()


def lock_path_for_db(db_path: Path) -> Path:
    return Path(f"{db_path}.lock")


def open_pipeline_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=DEFAULT_BUSY_TIMEOUT_MS / 1000.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={DEFAULT_BUSY_TIMEOUT_MS}")
    return conn


def wal_checkpoint_truncate(conn: sqlite3.Connection) -> tuple[int, int, int]:
    rows = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    if rows is None:
        return 0, 0, 0
    busy, log_frames, checkpointed = rows
    return int(busy), int(log_frames), int(checkpointed)


def acquire_daemon_lock(db_path: Path) -> DaemonSession:
    lock_path = lock_path_for_db(db_path)
    advisory = _AdvisoryPipelineLock(lock_path)
    conn = open_pipeline_connection(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.commit()
    return DaemonSession(
        db_path=db_path,
        lock_path=lock_path,
        owner_id=uuid.uuid4().hex,
        _advisory=advisory,
        connection=conn,
    )


def release_daemon_session(session: DaemonSession) -> None:
    if session.connection is not None:
        try:
            wal_checkpoint_truncate(session.connection)
        finally:
            session.connection.close()
            session.connection = None
    session._advisory.release()


def handle_sigterm(
    state: DaemonShutdownState,
    session: DaemonSession | None,
) -> None:
    """Release the pipeline lock and request a WAL TRUNCATE checkpoint."""
    if session is None:
        return
    if not state.lock_released:
        session._advisory.release()
        state.lock_released = True
    if session.connection is not None and not state.wal_checkpoint_requested:
        wal_checkpoint_truncate(session.connection)
        state.wal_checkpoint_requested = True


SigtermHandlerFactory = Callable[[DaemonSession], tuple[Callable[[int, object], None], DaemonShutdownState]]


def make_sigterm_handler(
    session: DaemonSession,
    *,
    state: DaemonShutdownState | None = None,
) -> tuple[Callable[[int, object], None], DaemonShutdownState]:
    shutdown = state if state is not None else DaemonShutdownState()

    def _on_sigterm(signum: int, frame: object) -> None:  # noqa: ARG001
        handle_sigterm(shutdown, session)

    return _on_sigterm, shutdown


def register_sigterm_handler(session: DaemonSession) -> DaemonShutdownState:
    handler, state = make_sigterm_handler(session)
    signal.signal(signal.SIGTERM, handler)
    return state