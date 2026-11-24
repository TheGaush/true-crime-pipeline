"""Tests for the sole-writer SQLite WAL driver.

Cross-process ownership is covered by a subprocess that holds the advisory lock.
In-process writers are covered by threads sharing one PipelineDb (the RLock).
The SQLite version gate is injected, so pass and fail both run on hosts whose
linked SQLite is older than 3.51.3.
"""

from __future__ import annotations

import errno
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
_REPO = Path(__file__).resolve().parents[3]


def _load_db_package():
    existing = sys.modules.get("db")
    if existing is not None and hasattr(existing, "PipelineDb"):
        return existing
    spec = importlib.util.spec_from_file_location(
        "db",
        _SRC / "__init__.py",
        submodule_search_locations=[str(_SRC)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load db package from {_SRC}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["db"] = module
    spec.loader.exec_module(module)
    return module


_load_db_package()

import db.connection as connection  # noqa: E402
from db import (  # noqa: E402
    MIN_SQLITE_VERSION,
    NetworkPathError,
    PipelineDb,
    SoleWriterOccupiedError,
    SqliteVersionError,
)

ACCEPTED = (3, 51, 3)
AUDIT_AND_META_SQL = """
CREATE TABLE meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE audit_log (
  audit_seq INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id TEXT NOT NULL,
  action_type TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at INTEGER NOT NULL
);
"""
HOLDER_SCRIPT = """
import importlib.util
import sys
import time
from pathlib import Path

src = Path(sys.argv[1])
db_path = sys.argv[2]
spec = importlib.util.spec_from_file_location(
    "db",
    src / "__init__.py",
    submodule_search_locations=[str(src)],
)
module = importlib.util.module_from_spec(spec)
sys.modules["db"] = module
spec.loader.exec_module(module)
schema = (
    "CREATE TABLE meta ("
    "key TEXT PRIMARY KEY, "
    "value TEXT NOT NULL"
    ");"
)
db = module.PipelineDb(db_path, sqlite_version=(3, 51, 3), schema_sql=schema)
rows = db.execute(
    "SELECT value FROM meta WHERE key = ?",
    ("sole_writer_owner",),
)
print("HEARTBEAT " + rows[0][0], flush=True)
print("READY", flush=True)
time.sleep(120)
db.close()
"""


def _busy(message: str = "database is locked") -> sqlite3.OperationalError:
    error = sqlite3.OperationalError(message)
    error.sqlite_errorcode = sqlite3.SQLITE_BUSY
    return error


def _readline(proc: subprocess.Popen[str], timeout: float) -> str:
    box: dict[str, str] = {}

    def target() -> None:
        assert proc.stdout is not None
        box["line"] = proc.stdout.readline()

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        proc.kill()
        proc.wait(timeout=10)
        err = proc.stderr.read() if proc.stderr is not None else ""
        raise AssertionError(f"timed out waiting for holder output\n{err}")
    return box.get("line", "")


def _open(path: Path, **kwargs) -> PipelineDb:
    kwargs.setdefault("sqlite_version", ACCEPTED)
    return PipelineDb(path, **kwargs)


def test_package_reexports_pipeline_db() -> None:
    assert MIN_SQLITE_VERSION == (3, 51, 3)
    assert PipelineDb is connection.PipelineDb


@pytest.mark.parametrize("version", [(3, 51, 3), (3, 51, 4), (3, 52, 0), (4, 0, 1)])
def test_injected_version_at_least_minimum_opens(tmp_path: Path, version: tuple[int, int, int]) -> None:
    path = tmp_path / f"ok-{version[0]}-{version[1]}-{version[2]}.db"
    with _open(path, sqlite_version=version) as db:
        assert db.accepted_version == version
        assert db.version_source == "injected"
        assert db.lock_path == Path(str(db.path) + ".lock")
        assert db.lock_path.parent == db.path.parent
        assert db.execute("PRAGMA journal_mode")[0][0].lower() == "wal"


@pytest.mark.parametrize("version", [(3, 51, 2), (3, 49, 1), (3, 0, 0)])
def test_injected_version_older_than_minimum_raises(tmp_path: Path, version: tuple[int, int, int]) -> None:
    path = tmp_path / "too-old.db"
    with pytest.raises(SqliteVersionError) as caught:
        PipelineDb(path, sqlite_version=version)
    assert caught.value.found == version
    assert caught.value.required == (3, 51, 3)
    assert not path.exists()
    assert not Path(str(path) + ".lock").exists()


def test_omitted_version_reads_runtime_tuple(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(connection.sqlite3, "sqlite_version_info", (3, 51, 3))
    with PipelineDb(tmp_path / "runtime-ok.db") as db:
        assert db.version_source == "runtime"
        assert db.accepted_version == (3, 51, 3)


def test_omitted_version_rejects_old_runtime_tuple(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(connection.sqlite3, "sqlite_version_info", (3, 51, 2))
    path = tmp_path / "runtime-old.db"
    with pytest.raises(SqliteVersionError) as caught:
        PipelineDb(path)
    assert caught.value.found == (3, 51, 2)
    assert not path.exists()


@pytest.mark.parametrize(
    "raw",
    [r"\\server\share\pipeline.db", "//server/share/pipeline.db"],
)
def test_unc_paths_are_rejected_without_opening(raw: str) -> None:
    with pytest.raises(NetworkPathError):
        PipelineDb(raw, sqlite_version=ACCEPTED)


@pytest.mark.parametrize("kind", ["smb", "nfs", "unc", "network", "SMB"])
def test_network_classifier_hook_rejects_local_looking_path(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "pipeline.db"
    seen: list[str] = []

    def classify(candidate: str | Path) -> str:
        seen.append(os.fspath(candidate))
        return kind

    with pytest.raises(NetworkPathError):
        PipelineDb(path, sqlite_version=ACCEPTED, path_classifier=classify)
    assert seen
    assert not path.exists()
    assert not Path(str(path) + ".lock").exists()


def test_unc_prefix_wins_over_classifier_that_says_local() -> None:
    with pytest.raises(NetworkPathError):
        PipelineDb(
            r"\\fileserver\share\pipeline.db",
            sqlite_version=ACCEPTED,
            path_classifier=lambda _path: "local",
        )


def test_local_temp_path_sets_required_pragmas(tmp_path: Path) -> None:
    with _open(tmp_path / "pipeline.db") as db:
        assert db.path.is_absolute()
        assert str(db.execute("PRAGMA journal_mode")[0][0]).lower() == "wal"
        assert int(db.execute("PRAGMA synchronous")[0][0]) == 2
        assert int(db.execute("PRAGMA foreign_keys")[0][0]) == 1
        assert int(db.execute("PRAGMA busy_timeout")[0][0]) == 5000
        assert db.last_begin_sql == "BEGIN DEFERRED"
        db.execute("CREATE TABLE ticks (id INTEGER PRIMARY KEY)", write=True)
        assert db.last_begin_sql == "BEGIN IMMEDIATE"
        assert db.begin_immediate_count >= 1
        assert db.open_cursor_count == 0


def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    with _open(tmp_path / "fk.db") as db:
        db.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)", write=True)
        db.execute(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id))",
            write=True,
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO child (id, parent_id) VALUES (1, 9)", write=True)
        assert db.open_cursor_count == 0


def test_blank_database_does_not_insert_audit_until_table_exists(tmp_path: Path) -> None:
    with _open(tmp_path / "blank.db") as db:
        present = db.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = 'audit_log'"
        )[0][0]
        assert present == 0
        assert db.refresh_owner_heartbeat() is False
        db.apply_schema(AUDIT_AND_META_SQL)
        rows = db.execute(
            "SELECT actor_id, action_type, entity_type, entity_id, detail_json FROM audit_log"
        )
        assert len(rows) == 1
        assert rows[0][0] == "pipeline_db"
        assert rows[0][1] == "sqlite_runtime_started"
        assert rows[0][2] == "sqlite"
        assert rows[0][3] == "runtime"
        detail = json.loads(rows[0][4])
        assert detail["sqlite_version"] == sqlite3.sqlite_version
        assert detail["accepted_version_info"] == list(ACCEPTED)
        assert detail["min_sqlite_version"] == [3, 51, 3]
        owner = json.loads(
            db.execute("SELECT value FROM meta WHERE key = 'sole_writer_owner'")[0][0]
        )
        assert owner["pid"] == os.getpid()
        assert owner["owner_id"] == db.owner_id
        assert db.open_cursor_count == 0


def test_context_manager_closes_cursors_connection_and_lock(tmp_path: Path) -> None:
    path = tmp_path / "life.db"
    with _open(path) as db:
        with db.write() as cursor:
            cursor.execute("CREATE TABLE t (id INTEGER)")
            assert db.open_cursor_count == 1
        assert db.open_cursor_count == 0
        with pytest.raises(RuntimeError, match="boom"):
            with db.write() as cursor:
                cursor.execute("INSERT INTO t (id) VALUES (1)")
                raise RuntimeError("boom")
        assert db.open_cursor_count == 0
        assert db.execute("SELECT COUNT(*) FROM t")[0][0] == 0
        with pytest.raises(sqlite3.IntegrityError):
            with db.write() as cursor:
                cursor.execute("CREATE TABLE once (id INTEGER PRIMARY KEY)")
                cursor.execute("INSERT INTO once (id) VALUES (1)")
                cursor.execute("INSERT INTO once (id) VALUES (1)")
        assert db.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'once'") == []
        assert db.open_cursor_count == 0
    assert db.closed
    with pytest.raises(RuntimeError, match="closed"):
        db.execute("SELECT 1")
    with _open(path) as reopened:
        assert reopened.execute("SELECT COUNT(*) FROM t")[0][0] == 0


def test_trigger_body_stays_one_statement(tmp_path: Path) -> None:
    sql = """
    -- leading comment must stay attached to the next statement
    CREATE TABLE t (id INTEGER PRIMARY KEY);
    CREATE TRIGGER trg BEFORE INSERT ON t
    BEGIN
      SELECT RAISE(ABORT, 'blocked');
    END;
    """
    statements = connection.split_sql_script(sql)
    assert len(statements) == 2
    assert "RAISE" in statements[1]
    with _open(tmp_path / "trigger.db", schema_sql=sql) as db:
        with pytest.raises(sqlite3.IntegrityError, match="blocked"):
            db.execute("INSERT INTO t (id) VALUES (1)", write=True)


def test_checkpoints_passive_and_truncate(tmp_path: Path) -> None:
    with _open(tmp_path / "ckpt.db") as db:
        db.execute("CREATE TABLE t (id INTEGER)", write=True)
        db.execute("INSERT INTO t (id) VALUES (7)", write=True)
        passive = db.checkpoint_passive()
        truncated = db.checkpoint_truncate()
        assert len(passive) == 3
        assert len(truncated) == 3
        assert truncated[0] == 0
        assert db.execute("SELECT id FROM t")[0][0] == 7
        assert db.open_cursor_count == 0


def test_retry_busy_and_ebusy_are_bounded() -> None:
    sleeps: list[float] = []

    def always_busy() -> None:
        raise _busy()

    with pytest.raises(sqlite3.OperationalError):
        connection.run_with_busy_retry(
            always_busy,
            attempts=4,
            base_delay=0.01,
            max_delay=0.05,
            sleep=sleeps.append,
            uniform=lambda _low, _high: 1.0,
        )
    assert sleeps == [0.01, 0.02, 0.04]
    assert all(delay <= 0.05 for delay in sleeps)

    jitter: list[float] = []
    calls = {"n": 0}

    def succeed_on_third() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError(errno.EBUSY, "busy")
        return "ok"

    result = connection.run_with_busy_retry(
        succeed_on_third,
        attempts=5,
        base_delay=0.02,
        max_delay=0.05,
        sleep=jitter.append,
        uniform=lambda _low, _high: 0.5,
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert len(jitter) == 2
    assert jitter[0] == pytest.approx(0.01)
    assert jitter[1] == pytest.approx(0.02)
    assert all(delay <= 0.05 for delay in jitter)

    message_only = sqlite3.OperationalError("database is busy")
    assert connection.is_retryable_busy(message_only)
    assert connection.is_retryable_busy(_busy())
    assert connection.is_retryable_busy(OSError(errno.EBUSY, "busy"))
    assert not connection.is_retryable_busy(OSError(errno.EACCES, "denied"))
    assert not connection.is_retryable_busy(sqlite3.IntegrityError("no"))

    no_sleep: list[float] = []

    def fail_integrity() -> None:
        raise sqlite3.IntegrityError("constraint")

    with pytest.raises(sqlite3.IntegrityError):
        connection.run_with_busy_retry(fail_integrity, attempts=4, sleep=no_sleep.append)
    assert no_sleep == []


@pytest.mark.parametrize(
    "make_error",
    [lambda: _busy(), lambda: OSError(errno.EBUSY, "busy")],
)
def test_write_retries_begin_immediate(tmp_path: Path, make_error) -> None:
    db = _open(tmp_path / "retry.db", retry_attempts=4, sleep=lambda _delay: None)
    try:
        calls = {"n": 0}
        real_begin = db._begin_once

        def wrapped(sql: str) -> None:
            if sql == "BEGIN IMMEDIATE":
                calls["n"] += 1
                if calls["n"] < 3:
                    raise make_error()
            return real_begin(sql)

        db._begin_once = wrapped  # type: ignore[method-assign]
        db.execute("CREATE TABLE t (id INTEGER)", write=True)
        assert calls["n"] == 3
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name = 't'")[0][0] == 1
        assert db.open_cursor_count == 0
    finally:
        db.close()


def test_rlock_serializes_in_process_writers(tmp_path: Path) -> None:
    db = _open(tmp_path / "serial.db")
    try:
        db.execute("CREATE TABLE t (n INTEGER)", write=True)
        state = {"current": 0, "max": 0}
        guard = threading.Lock()

        def worker() -> None:
            with db.write() as cursor:
                with guard:
                    state["current"] += 1
                    state["max"] = max(state["max"], state["current"])
                time.sleep(0.02)
                cursor.execute("INSERT INTO t (n) VALUES (1)")
                with guard:
                    state["current"] -= 1

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert all(not thread.is_alive() for thread in threads)
        assert state["max"] == 1
        assert state["current"] == 0
        assert db.max_active_writers == 1
        assert db.execute("SELECT COUNT(*) FROM t")[0][0] == 8
        assert db.open_cursor_count == 0
    finally:
        db.close()


def test_second_instance_in_process_cannot_become_writer(tmp_path: Path) -> None:
    path = tmp_path / "one-writer.db"
    holder = _open(path, schema_sql=AUDIT_AND_META_SQL)
    try:
        with pytest.raises(SoleWriterOccupiedError):
            _open(path)
        holder.execute("CREATE TABLE still_owner (id INTEGER)", write=True)
        owner = json.loads(
            holder.execute("SELECT value FROM meta WHERE key = 'sole_writer_owner'")[0][0]
        )
        assert owner["owner_id"] == holder.owner_id
    finally:
        holder.close()
    with _open(path) as successor:
        assert successor.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'still_owner'"
        ) == [("still_owner",)]


def test_second_process_cannot_become_writer(tmp_path: Path) -> None:
    """Spawn one holder process. A second PipelineDb in this process must fail.

    This is a real process boundary, not only a thread or same-process lock test.
    """

    db_path = tmp_path / "pipeline.db"
    script = tmp_path / "hold_writer.py"
    script.write_text(HOLDER_SCRIPT, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script), str(_SRC), str(db_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        heartbeat_line = _readline(proc, 90)
        ready_line = _readline(proc, 90)
        if not heartbeat_line.startswith("HEARTBEAT ") or ready_line.strip() != "READY":
            proc.kill()
            proc.wait(timeout=10)
            err = proc.stderr.read() if proc.stderr is not None else ""
            raise AssertionError(
                f"holder failed to start\nstdout={heartbeat_line!r} {ready_line!r}\n{err}"
            )
        heartbeat = json.loads(heartbeat_line.removeprefix("HEARTBEAT ").strip())
        assert heartbeat["pid"] == proc.pid
        with pytest.raises(SoleWriterOccupiedError):
            _open(db_path)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stderr is not None:
            proc.stderr.close()

    with _open(db_path) as successor:
        owner = json.loads(
            successor.execute("SELECT value FROM meta WHERE key = 'sole_writer_owner'")[0][0]
        )
        assert owner["pid"] == os.getpid()
        assert owner["owner_id"] == successor.owner_id


def test_sixteen_threads_report_zero_unhandled_sqlite_busy(tmp_path: Path) -> None:
    path = tmp_path / "stress.db"
    try:
        db = _open(path, sleep=lambda _delay: None)
    except connection.WalModeError as exc:
        pytest.skip(f"host SQLite cannot open WAL: {exc}")

    threads_n = 16
    per_thread = 20
    busy: list[str] = []
    errors: list[str] = []
    barrier = threading.Barrier(threads_n)
    try:
        mode = str(db.execute("PRAGMA journal_mode")[0][0]).lower()
        if mode != "wal":
            pytest.skip(f"host SQLite cannot open WAL (journal_mode={mode})")
        db.execute("CREATE TABLE ticks (n INTEGER PRIMARY KEY)", write=True)

        def worker(index: int) -> None:
            try:
                barrier.wait(30)
                for step in range(per_thread):
                    db.execute(
                        "INSERT INTO ticks (n) VALUES (?)",
                        (index * per_thread + step,),
                        write=True,
                    )
            except Exception as exc:
                if connection.is_retryable_busy(exc):
                    busy.append(repr(exc))
                else:
                    errors.append(traceback.format_exc())

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(threads_n)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        assert all(not thread.is_alive() for thread in threads)
        assert busy == []
        assert errors == []
        assert db.execute("SELECT COUNT(*) FROM ticks")[0][0] == threads_n * per_thread
        assert db.max_active_writers == 1
        assert db.open_cursor_count == 0
        assert db.checkpoint_truncate()[0] == 0
    finally:
        db.close()


def test_real_pipeline_schema_when_present(tmp_path: Path) -> None:
    schema_path = _REPO / "schema" / "pipeline.sql"
    if not schema_path.is_file():
        pytest.skip("schema/pipeline.sql is not in the worktree")
    sql = schema_path.read_text(encoding="utf-8")
    with _open(tmp_path / "pipeline.db", schema_sql=sql) as db:
        assert db.execute("SELECT value FROM meta WHERE key = 'schema_version'") == [("4",)]
        detail = json.loads(db.execute("SELECT detail_json FROM audit_log")[0][0])
        assert detail["sqlite_version"] == sqlite3.sqlite_version
        owner = json.loads(
            db.execute("SELECT value FROM meta WHERE key = 'sole_writer_owner'")[0][0]
        )
        assert owner["pid"] == os.getpid()
        assert db.refresh_owner_heartbeat() is True
        assert db.open_cursor_count == 0
        assert db.checkpoint_passive()[2] >= 0
        assert db.checkpoint_truncate()[0] == 0


def test_advisory_lock_second_handle_fails_without_sqlite(tmp_path: Path) -> None:
    lock_path = tmp_path / "pipeline.db.lock"
    first = connection._AdvisoryFileLock(lock_path)
    try:
        with pytest.raises(SoleWriterOccupiedError):
            connection._AdvisoryFileLock(lock_path)
    finally:
        first.release()
    second = connection._AdvisoryFileLock(lock_path)
    second.release()
