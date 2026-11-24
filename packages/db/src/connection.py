"""Sole-writer SQLite WAL driver for ``pipeline.db``.

Production startup reads ``sqlite3.sqlite_version_info`` and refuses anything
older than 3.51.3. Tests may pass ``sqlite_version`` so that gate can pass or
fail without depending on the SQLite library linked into the host interpreter.
Omit ``sqlite_version`` outside tests.
"""

from __future__ import annotations

import errno
import json
import logging
import os
import random
import socket
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

MIN_SQLITE_VERSION: tuple[int, int, int] = (3, 51, 3)
BUSY_TIMEOUT_MS = 5000
META_OWNER_KEY = "sole_writer_owner"
AUDIT_COLUMNS = (
    "actor_id",
    "action_type",
    "entity_type",
    "entity_id",
    "detail_json",
    "created_at",
)
DEFAULT_RETRY_ATTEMPTS = 6
DEFAULT_RETRY_BASE_DELAY_S = 0.005
DEFAULT_RETRY_MAX_DELAY_S = 0.08

T = TypeVar("T")
SqlParams = Sequence[Any] | dict[str, Any]
SleepFn = Callable[[float], None]
UniformFn = Callable[[float, float], float]
PathClassifier = Callable[[str | Path], str]


class PipelineDbError(Exception):
    """Base error for the sole-writer driver."""


class SqliteVersionError(PipelineDbError):
    """The SQLite runtime (or the injected test tuple) is older than 3.51.3."""

    def __init__(
        self,
        found: tuple[int, ...],
        required: tuple[int, int, int] = MIN_SQLITE_VERSION,
    ) -> None:
        self.found = tuple(found)
        self.required = tuple(required)
        found_text = ".".join(str(part) for part in self.found)
        required_text = ".".join(str(part) for part in self.required)
        super().__init__(
            f"SQLite {found_text} is older than required {required_text}"
        )


class NetworkPathError(PipelineDbError):
    """The database path is UNC or was classified as SMB/NFS/network storage."""


class SoleWriterOccupiedError(PipelineDbError):
    """Another process already holds the sole-writer advisory lock."""


class WalModeError(PipelineDbError):
    """SQLite opened the file but journal_mode did not stick at WAL."""


def classify_database_path(path: str | Path) -> str:
    """Return ``unc`` for Windows UNC paths and ``local`` otherwise.

    Detection is prefix-only. It does not stat the path, resolve symlinks, or
    ask Windows whether a drive letter is a network mount (those calls can
    touch the network). Pass ``path_classifier`` to PipelineDb for mapped
    SMB/NFS shares that do not start with ``\\\\`` or ``//``.
    """

    text = os.fspath(path)
    if text.startswith("\\\\") or text.startswith("//"):
        return "unc"
    return "local"


def assert_local_database_path(
    path: str | Path,
    *,
    classifier: PathClassifier | None = None,
) -> None:
    """Reject UNC paths and any classifier result other than ``local``."""

    text = os.fspath(path)
    if text.strip() == "":
        raise ValueError("database path is empty")
    kind = classify_database_path(text)
    if kind == "local" and classifier is not None:
        kind = str(classifier(path))
    if kind.strip().lower() != "local":
        raise NetworkPathError(f"refusing non-local database path ({kind}): {text}")


def coerce_sqlite_version(version: tuple[int, ...]) -> tuple[int, int, int]:
    if len(version) < 3:
        raise SqliteVersionError(tuple(version))
    return (int(version[0]), int(version[1]), int(version[2]))


def assert_sqlite_version(version: tuple[int, ...]) -> tuple[int, int, int]:
    """Raise ``SqliteVersionError`` when ``version`` is older than 3.51.3."""

    found = coerce_sqlite_version(version)
    if found < MIN_SQLITE_VERSION:
        raise SqliteVersionError(found)
    return found


def is_retryable_busy(exc: BaseException) -> bool:
    """True for SQLITE_BUSY (including extended codes) and Windows EBUSY."""

    if isinstance(exc, sqlite3.OperationalError):
        code = getattr(exc, "sqlite_errorcode", None)
        if isinstance(code, int) and (code & 0xFF) == sqlite3.SQLITE_BUSY:
            return True
        message = str(exc).lower()
        return "database is locked" in message or "database is busy" in message
    return isinstance(exc, OSError) and exc.errno == errno.EBUSY


def run_with_busy_retry(
    operation: Callable[[], T],
    *,
    attempts: int = DEFAULT_RETRY_ATTEMPTS,
    base_delay: float = DEFAULT_RETRY_BASE_DELAY_S,
    max_delay: float = DEFAULT_RETRY_MAX_DELAY_S,
    sleep: SleepFn = time.sleep,
    uniform: UniformFn = random.uniform,
) -> T:
    """Run ``operation`` with bounded jitter retries on busy errors.

    Delay for attempt ``n`` (0-based, after a failure) is
    ``min(max_delay, base_delay * 2**n) * uniform(0.5, 1.0)``.
    The final attempt does not sleep.
    """

    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    if base_delay < 0 or max_delay < 0:
        raise ValueError("retry delays must be >= 0")
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if not is_retryable_busy(exc) or attempt == attempts - 1:
                raise
            delay = min(max_delay, base_delay * (2**attempt))
            delay *= uniform(0.5, 1.0)
            if delay > 0:
                sleep(delay)
    raise RuntimeError("busy retry loop exited without a result")


def split_sql_script(sql: str) -> list[str]:
    """Split a SQL script into complete statements.

    Uses ``sqlite3.complete_statement`` so trigger bodies keep their internal
    semicolons. Trailing comments are ignored.
    """

    if sql.startswith("\ufeff"):
        sql = sql[1:]
    statements: list[str] = []
    buffer = ""
    for line in sql.splitlines(keepends=True):
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement and not _comment_only(statement):
                statements.append(statement)
    trailing = buffer.strip()
    if trailing and not _comment_only(trailing):
        raise ValueError("schema sql ended with an incomplete statement")
    return statements


def _comment_only(statement: str) -> bool:
    stripped = _strip_sql_comments(statement).strip()
    return stripped == "" or stripped == ";"


def _strip_sql_comments(sql: str) -> str:
    out: list[str] = []
    index = 0
    length = len(sql)
    in_single = False
    in_double = False
    while index < length:
        char = sql[index]
        nxt = sql[index + 1] if index + 1 < length else ""
        if in_single:
            out.append(char)
            if char == "'" and nxt == "'":
                out.append(nxt)
                index += 2
                continue
            if char == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            out.append(char)
            if char == '"':
                in_double = False
            index += 1
            continue
        if char == "'":
            in_single = True
            out.append(char)
            index += 1
            continue
        if char == '"':
            in_double = True
            out.append(char)
            index += 1
            continue
        if char == "-" and nxt == "-":
            index += 2
            while index < length and sql[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and nxt == "*":
            index += 2
            while index + 1 < length and not (sql[index] == "*" and sql[index + 1] == "/"):
                index += 1
            index = min(length, index + 2)
            continue
        out.append(char)
        index += 1
    return "".join(out)


class _AdvisoryFileLock:
    """Exclusive advisory lock using ``msvcrt`` on Windows and ``fcntl`` elsewhere.

    The lock file lives next to the database (``pipeline.db`` -> ``pipeline.db.lock``).
    A second process fails immediately instead of becoming a writer.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None
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
                raise SoleWriterOccupiedError(
                    f"sole-writer lock is already held: {self.path}"
                ) from exc
            return
        import fcntl

        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise SoleWriterOccupiedError(
                f"sole-writer lock is already held: {self.path}"
            ) from exc

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


class PipelineDb:
    """In-process and cross-process sole writer for one SQLite database.

    One connection is shared across threads. ``threading.RLock`` serializes
    every use of that connection. Writes run in ``BEGIN IMMEDIATE``. Reads run
    in short ``BEGIN DEFERRED`` transactions. Both close the cursor they open.

    Cross-process ownership is an OS advisory lock plus a ``meta`` heartbeat
    (``sole_writer_owner``) when that table exists. Periodic WAL checkpoints
    are ``checkpoint_passive`` and ``checkpoint_truncate``; callers schedule them.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        sqlite_version: tuple[int, ...] | None = None,
        schema_sql: str | None = None,
        path_classifier: PathClassifier | None = None,
        owner_id: str | None = None,
        retry_attempts: int = DEFAULT_RETRY_ATTEMPTS,
        retry_base_delay: float = DEFAULT_RETRY_BASE_DELAY_S,
        retry_max_delay: float = DEFAULT_RETRY_MAX_DELAY_S,
        sleep: SleepFn = time.sleep,
        uniform: UniformFn = random.uniform,
    ) -> None:
        self._rlock = threading.RLock()
        self._closed = False
        self._conn: sqlite3.Connection | None = None
        self._advisory: _AdvisoryFileLock | None = None
        self._cursors: list[sqlite3.Cursor] = []
        self._txn_depth = 0
        self._active_writers = 0
        self.max_active_writers = 0
        self.begin_immediate_count = 0
        self.last_begin_sql: str | None = None
        self._audited = False
        self.owner_id = owner_id or uuid.uuid4().hex
        self._attempts = retry_attempts
        self._base_delay = retry_base_delay
        self._max_delay = retry_max_delay
        self._sleep = sleep
        self._uniform = uniform
        self._path_classifier = path_classifier

        if sqlite_version is None:
            raw_version = tuple(sqlite3.sqlite_version_info)
            self.version_source = "runtime"
        else:
            raw_version = tuple(sqlite_version)
            self.version_source = "injected"
        self.accepted_version = assert_sqlite_version(raw_version)
        if schema_sql is not None and not str(schema_sql).strip():
            raise ValueError("schema_sql must be a non-empty SQL string")
        assert_local_database_path(path, classifier=path_classifier)
        self._path = _absolute_local_path(path)
        self._lock_path = Path(str(self._path) + ".lock")

        try:
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            self._advisory = _AdvisoryFileLock(self._lock_path)
            self._conn = sqlite3.connect(
                os.fspath(self._path),
                isolation_level=None,
                check_same_thread=False,
                timeout=BUSY_TIMEOUT_MS / 1000,
            )
            self._apply_pragmas()
            logger.info(
                "active SQLite %s; version gate accepted %s",
                sqlite3.sqlite_version,
                ".".join(str(part) for part in self.accepted_version),
            )
            if schema_sql is not None:
                self.apply_schema(schema_sql)
            else:
                self._record_startup()
        except Exception:
            self.close()
            raise

    def __enter__(self) -> PipelineDb:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __repr__(self) -> str:
        state = "closed" if self._closed else "open"
        return f"PipelineDb({str(self._path)!r}, {state})"

    @property
    def path(self) -> Path:
        return self._path

    @property
    def lock_path(self) -> Path:
        return self._lock_path

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def open_cursor_count(self) -> int:
        with self._rlock:
            return len(self._cursors)

    def close(self) -> None:
        """Close every tracked cursor, the connection, and the advisory lock."""

        with self._rlock:
            if self._closed and self._conn is None and self._advisory is None:
                return
            self._closed = True
            for cursor in list(self._cursors):
                self._close_cursor(cursor)
            self._cursors.clear()
            connection = self._conn
            self._conn = None
            if connection is not None:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
                connection.close()
            advisory = self._advisory
            self._advisory = None
            if advisory is not None:
                advisory.release()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            return

    def apply_schema(self, sql: str) -> None:
        """Apply a SQL script under ``BEGIN IMMEDIATE``.

        Pass ``schema/pipeline.sql`` (or a tiny stand-in) as a string. This
        package does not embed the pipeline schema. When ``audit_log`` or
        ``meta`` exist after the script, startup audit and the owner heartbeat
        are written in the same transaction.
        """

        statements = split_sql_script(sql)
        if not statements:
            raise ValueError("schema sql has no statements")

        def run(cursor: sqlite3.Cursor) -> bool:
            for statement in statements:
                cursor.execute(statement)
            inserted = self._insert_audit(cursor)
            self._upsert_heartbeat(cursor)
            return inserted

        if self._immediate(run):
            self._audited = True
        with self._rlock:
            self._check_open()
            self._apply_pragmas()

    def refresh_owner_heartbeat(self) -> bool:
        """Refresh ``meta.sole_writer_owner`` when the ``meta`` table exists."""

        if not self._table_exists("meta"):
            return False

        def run(cursor: sqlite3.Cursor) -> bool:
            return self._upsert_heartbeat(cursor)

        return bool(self._immediate(run))

    def checkpoint_passive(self) -> tuple[int, int, int]:
        """Run ``PRAGMA wal_checkpoint(PASSIVE)`` outside a user transaction."""

        return self._checkpoint("PASSIVE")

    def checkpoint_truncate(self) -> tuple[int, int, int]:
        """Run ``PRAGMA wal_checkpoint(TRUNCATE)`` outside a user transaction."""

        return self._checkpoint("TRUNCATE")

    @contextmanager
    def write(self) -> Iterator[sqlite3.Cursor]:
        """``BEGIN IMMEDIATE`` under the process RLock. Closes the cursor."""

        with self._writer_scope():
            self._begin_with_retry("BEGIN IMMEDIATE")
            self._txn_depth += 1
            cursor = self._new_cursor()
            try:
                try:
                    yield cursor
                    self._commit_with_retry()
                except Exception:
                    self._rollback_quiet()
                    raise
            finally:
                self._txn_depth -= 1
                self._close_cursor(cursor)

    @contextmanager
    def read(self) -> Iterator[sqlite3.Cursor]:
        """Short ``BEGIN DEFERRED`` read. Closes the cursor."""

        with self._writer_scope(count_writer=False):
            self._begin_with_retry("BEGIN DEFERRED")
            self._txn_depth += 1
            cursor = self._new_cursor()
            try:
                try:
                    yield cursor
                    self._commit_with_retry()
                except Exception:
                    self._rollback_quiet()
                    raise
            finally:
                self._txn_depth -= 1
                self._close_cursor(cursor)

    def execute(
        self,
        sql: str,
        params: SqlParams = (),
        *,
        write: bool = False,
    ) -> list[tuple] | int:
        """Run one statement. ``write=True`` uses ``BEGIN IMMEDIATE``.

        Writes return ``rowcount``. Reads return the fetched rows. The cursor
        is closed before this method returns.
        """

        manager = self.write() if write else self.read()
        with manager as cursor:
            cursor.execute(sql, params)
            if write:
                return cursor.rowcount
            return cursor.fetchall()

    def _record_startup(self) -> None:
        if not self._table_exists("audit_log") and not self._table_exists("meta"):
            return

        def run(cursor: sqlite3.Cursor) -> bool:
            inserted = self._insert_audit(cursor)
            self._upsert_heartbeat(cursor)
            return inserted

        if self._immediate(run):
            self._audited = True

    def _immediate(self, fn: Callable[[sqlite3.Cursor], T]) -> T:
        """Run ``fn`` inside one retried ``BEGIN IMMEDIATE`` transaction."""

        def attempt() -> T:
            self._begin_once("BEGIN IMMEDIATE")
            self._txn_depth += 1
            cursor = self._new_cursor()
            try:
                try:
                    result = fn(cursor)
                    self._commit_once()
                    return result
                except Exception:
                    self._rollback_quiet()
                    raise
            finally:
                self._txn_depth -= 1
                self._close_cursor(cursor)

        with self._writer_scope():
            return run_with_busy_retry(
                attempt,
                attempts=self._attempts,
                base_delay=self._base_delay,
                max_delay=self._max_delay,
                sleep=self._sleep,
                uniform=self._uniform,
            )

    @contextmanager
    def _writer_scope(self, *, count_writer: bool = True) -> Iterator[None]:
        with self._rlock:
            self._check_open()
            if self._txn_depth:
                raise RuntimeError("nested PipelineDb transactions are not supported")
            if count_writer:
                self._active_writers += 1
                self.max_active_writers = max(self.max_active_writers, self._active_writers)
            try:
                yield
            finally:
                if count_writer:
                    self._active_writers -= 1

    def _begin_with_retry(self, sql: str) -> None:
        run_with_busy_retry(
            lambda: self._begin_once(sql),
            attempts=self._attempts,
            base_delay=self._base_delay,
            max_delay=self._max_delay,
            sleep=self._sleep,
            uniform=self._uniform,
        )

    def _commit_with_retry(self) -> None:
        run_with_busy_retry(
            self._commit_once,
            attempts=self._attempts,
            base_delay=self._base_delay,
            max_delay=self._max_delay,
            sleep=self._sleep,
            uniform=self._uniform,
        )

    def _begin_once(self, sql: str) -> None:
        connection = self._require_connection()
        cursor = connection.execute(sql)
        try:
            cursor.fetchall()
        finally:
            cursor.close()
        self.last_begin_sql = sql
        if sql == "BEGIN IMMEDIATE":
            self.begin_immediate_count += 1

    def _commit_once(self) -> None:
        connection = self._require_connection()
        cursor = connection.execute("COMMIT")
        cursor.close()

    def _rollback_quiet(self) -> None:
        connection = self._conn
        if connection is None:
            return
        try:
            cursor = connection.execute("ROLLBACK")
            cursor.close()
        except sqlite3.Error:
            return

    def _apply_pragmas(self) -> None:
        mode_rows = self._query_rows("PRAGMA journal_mode=WAL")
        mode = mode_rows[0][0] if mode_rows else None
        if str(mode).lower() != "wal":
            raise WalModeError(f"SQLite journal_mode is {mode!r}; WAL is required")
        self._query_rows("PRAGMA synchronous=FULL")
        self._query_rows("PRAGMA foreign_keys=ON")
        self._query_rows(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        synchronous = int(self._query_rows("PRAGMA synchronous")[0][0])
        foreign_keys = int(self._query_rows("PRAGMA foreign_keys")[0][0])
        busy_timeout = int(self._query_rows("PRAGMA busy_timeout")[0][0])
        if synchronous != 2 or foreign_keys != 1 or busy_timeout != BUSY_TIMEOUT_MS:
            raise WalModeError(
                "SQLite pragmas did not stick: "
                f"synchronous={synchronous} foreign_keys={foreign_keys} "
                f"busy_timeout={busy_timeout}"
            )

    def _checkpoint(self, mode: str) -> tuple[int, int, int]:
        if mode not in {"PASSIVE", "TRUNCATE"}:
            raise ValueError(f"unsupported checkpoint mode: {mode}")
        with self._rlock:
            self._check_open()
            if self._txn_depth:
                raise RuntimeError("cannot checkpoint WAL inside a transaction")
            rows = self._query_rows(f"PRAGMA wal_checkpoint({mode})")
        if not rows:
            return (0, 0, 0)
        busy, log_frames, checkpointed = rows[0]
        return int(busy), int(log_frames), int(checkpointed)

    def _table_exists(self, name: str) -> bool:
        with self._rlock:
            self._check_open()
            rows = self._query_rows(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            )
        return bool(rows)

    def _query_rows(self, sql: str, params: SqlParams = ()) -> list[tuple]:
        connection = self._require_connection()
        cursor = connection.cursor()
        self._cursors.append(cursor)
        try:
            cursor.execute(sql, params)
            return cursor.fetchall()
        finally:
            self._close_cursor(cursor)

    def _new_cursor(self) -> sqlite3.Cursor:
        cursor = self._require_connection().cursor()
        self._cursors.append(cursor)
        return cursor

    def _close_cursor(self, cursor: sqlite3.Cursor) -> None:
        try:
            cursor.close()
        except sqlite3.Error:
            pass
        try:
            self._cursors.remove(cursor)
        except ValueError:
            return

    def _require_connection(self) -> sqlite3.Connection:
        connection = self._conn
        if connection is None or self._closed:
            raise RuntimeError("PipelineDb is closed")
        return connection

    def _check_open(self) -> None:
        self._require_connection()

    def _insert_audit(self, cursor: sqlite3.Cursor) -> bool:
        if self._audited or not _has_columns(cursor, "audit_log", AUDIT_COLUMNS):
            return False
        detail = {
            "sqlite_version": sqlite3.sqlite_version,
            "sqlite_version_info": [int(part) for part in tuple(sqlite3.sqlite_version_info)[:3]],
            "accepted_version_info": list(self.accepted_version),
            "min_sqlite_version": list(MIN_SQLITE_VERSION),
        }
        cursor.execute(
            """
            INSERT INTO audit_log (
                actor_id, action_type, entity_type, entity_id, detail_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "pipeline_db",
                "sqlite_runtime_started",
                "sqlite",
                "runtime",
                json.dumps(detail, separators=(",", ":")),
                int(time.time() * 1000),
            ),
        )
        return True

    def _upsert_heartbeat(self, cursor: sqlite3.Cursor) -> bool:
        if not _has_columns(cursor, "meta", ("key", "value")):
            return False
        try:
            hostname = socket.gethostname() or "unknown"
        except OSError:
            hostname = "unknown"
        payload = {
            "owner_id": self.owner_id,
            "pid": os.getpid(),
            "hostname": hostname,
            "heartbeat_unix_ms": int(time.time() * 1000),
        }
        cursor.execute(
            """
            INSERT INTO meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (META_OWNER_KEY, json.dumps(payload, separators=(",", ":"))),
        )
        return True


def _has_columns(cursor: sqlite3.Cursor, table: str, required: tuple[str, ...]) -> bool:
    if table not in {"audit_log", "meta"}:
        raise ValueError(f"unsupported catalog table: {table}")
    cursor.execute(f'PRAGMA table_info("{table}")')
    present = {row[1] for row in cursor.fetchall()}
    return set(required).issubset(present)


def _absolute_local_path(path: str | Path) -> Path:
    candidate = Path(os.fspath(path))
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate
    return candidate
