"""SQLite bootstrap and backup-before-migrate migration runner.

Migration steps bump ``PRAGMA user_version`` by one per successful step.
Authoritative ``meta.schema_version`` in ``pipeline.db`` is set by
``schema/pipeline.sql`` (currently ``4``) and is only changed by explicit
migrations that update that meta key.
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TypeAlias

# Minimum runtime documented in schema/pipeline.sql (F-22); migrations use
# VACUUM INTO (available since SQLite 3.27).
MIN_SQLITE_VERSION_PIN = (3, 51, 3)

MAX_SCHEMA_VERSION = 4

Migration: TypeAlias = str | Callable[[sqlite3.Connection], None]

_DEFAULT_SCHEMA_DIR = "schema"
_PIPELINE_SQL = "pipeline.sql"
_TELEMETRY_SQL = "telemetry.sql"


class SchemaVersionTooNewError(RuntimeError):
    """Database ``meta.schema_version`` is newer than this code supports."""


class MigrationFailedError(RuntimeError):
    """A migration step failed; the database was restored from the pre-migrate snapshot."""


class BackupError(RuntimeError):
    """VACUUM INTO or pre-migrate verification failed; no schema changes were applied."""


def _repo_root(start: Path | None = None) -> Path:
    here = (start or Path(__file__)).resolve()
    for parent in (here, *here.parents):
        if (parent / "schema" / "pipeline.sql").is_file():
            return parent
    raise FileNotFoundError("Could not locate repo root (schema/pipeline.sql missing)")


def _snapshot_path(db_path: Path) -> Path:
    return db_path.with_name(db_path.name + ".pre-migrate.snapshot")


def _quick_check_ok(conn: sqlite3.Connection) -> bool:
    rows = conn.execute("PRAGMA quick_check").fetchall()
    return len(rows) == 1 and rows[0][0] == "ok"


def read_meta_schema_version(conn: sqlite3.Connection) -> int | None:
    try:
        row = conn.execute(
            "SELECT value FROM meta WHERE key = 'schema_version'"
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return int(row[0])


def assert_schema_version_supported(
    conn: sqlite3.Connection, *, max_version: int = MAX_SCHEMA_VERSION
) -> None:
    version = read_meta_schema_version(conn)
    if version is not None and version > max_version:
        raise SchemaVersionTooNewError(
            f"database schema_version {version} is newer than supported {max_version}"
        )


def vacuum_into_snapshot(conn: sqlite3.Connection, snapshot_path: Path) -> None:
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    if snapshot_path.exists():
        snapshot_path.unlink()
    # Escape single quotes for SQL string literal.
    dest = str(snapshot_path.resolve()).replace("'", "''")
    conn.execute(f"VACUUM INTO '{dest}'")


def _restore_db_from_snapshot(db_path: Path, snapshot_path: Path) -> None:
    shutil.copy2(snapshot_path, db_path)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(db_path) + suffix)
        if sidecar.exists():
            sidecar.unlink()


def _apply_one_migration(conn: sqlite3.Connection, step: Migration) -> None:
    if isinstance(step, str):
        conn.executescript(step)
        return
    step(conn)


class DbInitializer:
    """Create empty pipeline.db / telemetry.db files from repo DDL scripts."""

    def __init__(
        self,
        *,
        repo_root: Path | None = None,
        schema_dir: Path | None = None,
    ) -> None:
        self.repo_root = repo_root or _repo_root()
        self.schema_dir = schema_dir or (self.repo_root / _DEFAULT_SCHEMA_DIR)

    def _run_sql_file(self, db_path: Path, sql_name: str) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if db_path.exists():
            db_path.unlink()
        sql_path = self.schema_dir / sql_name
        script = sql_path.read_text(encoding="utf-8")
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(script)
            conn.commit()
        finally:
            conn.close()

    def init_pipeline(self, db_path: Path | str) -> int:
        path = Path(db_path)
        self._run_sql_file(path, _PIPELINE_SQL)
        conn = sqlite3.connect(path)
        try:
            version = read_meta_schema_version(conn)
            if version != MAX_SCHEMA_VERSION:
                raise RuntimeError(
                    f"expected meta.schema_version {MAX_SCHEMA_VERSION}, got {version!r}"
                )
            return version
        finally:
            conn.close()

    def init_telemetry(self, db_path: Path | str) -> None:
        self._run_sql_file(Path(db_path), _TELEMETRY_SQL)


class MigrationRunner:
    """Apply migrations inside a transaction after a verified VACUUM INTO snapshot."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        max_schema_version: int = MAX_SCHEMA_VERSION,
    ) -> None:
        self.db_path = Path(db_path)
        self.max_schema_version = max_schema_version

    def run(self, migrations: Sequence[Migration]) -> int:
        if not migrations:
            conn = sqlite3.connect(self.db_path)
            try:
                assert_schema_version_supported(
                    conn, max_version=self.max_schema_version
                )
                return conn.execute("PRAGMA user_version").fetchone()[0]
            finally:
                conn.close()

        snapshot = _snapshot_path(self.db_path)
        conn = sqlite3.connect(self.db_path)
        try:
            assert_schema_version_supported(
                conn, max_version=self.max_schema_version
            )
            try:
                vacuum_into_snapshot(conn, snapshot)
            except sqlite3.Error as exc:
                raise BackupError(f"VACUUM INTO failed: {exc}") from exc

            if not _quick_check_ok(conn):
                raise BackupError("PRAGMA quick_check failed before migration")

            user_version = conn.execute("PRAGMA user_version").fetchone()[0]
            conn.execute("BEGIN")
            try:
                for step in migrations:
                    _apply_one_migration(conn, step)
                    user_version += 1
                    conn.execute(f"PRAGMA user_version = {user_version}")
                conn.commit()
            except BaseException as exc:
                conn.rollback()
                conn.close()
                conn = None
                _restore_db_from_snapshot(self.db_path, snapshot)
                raise MigrationFailedError(
                    "migration failed; database restored from pre-migrate snapshot"
                ) from exc
            return user_version
        finally:
            if conn is not None:
                conn.close()