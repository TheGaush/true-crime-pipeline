from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from migrations import (  # noqa: E402
    DbInitializer,
    MigrationFailedError,
    MigrationRunner,
    SchemaVersionTooNewError,
    read_meta_schema_version,
)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture
def initializer(repo_root: Path, tmp_path: Path) -> DbInitializer:
    return DbInitializer(repo_root=repo_root)


def test_fresh_pipeline_init(initializer: DbInitializer, tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    version = initializer.init_pipeline(db_path)
    assert version == 4

    conn = sqlite3.connect(db_path)
    try:
        assert read_meta_schema_version(conn) == 4
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "meta" in tables
        assert "audit_log" in tables
    finally:
        conn.close()


def test_fresh_telemetry_init(initializer: DbInitializer, tmp_path: Path) -> None:
    db_path = tmp_path / "telemetry.db"
    initializer.init_telemetry(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "api_token_usage" in tables
        assert "render_timings" in tables
        assert read_meta_schema_version(conn) is None
    finally:
        conn.close()


def test_successful_migration_bumps_user_version(
    initializer: DbInitializer, tmp_path: Path
) -> None:
    db_path = tmp_path / "pipeline.db"
    initializer.init_pipeline(db_path)

    runner = MigrationRunner(db_path)

    def add_marker(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO audit_log "
            "(actor_id, action_type, entity_type, entity_id, created_at) "
            "VALUES ('test', 'migration_marker', 'meta', 'user_version', 1)"
        )

    new_version = runner.run([add_marker])
    assert new_version == 1

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
        count = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action_type = 'migration_marker'"
        ).fetchone()[0]
        assert count == 1
    finally:
        conn.close()


def test_failed_migration_restores_snapshot(
    initializer: DbInitializer, tmp_path: Path
) -> None:
    db_path = tmp_path / "pipeline.db"
    initializer.init_pipeline(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_log "
            "(actor_id, action_type, entity_type, entity_id, created_at) "
            "VALUES ('keeper', 'pre_migrate', 'meta', 'snapshot', 1)"
        )
        conn.commit()
        before = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        user_before = conn.execute("PRAGMA user_version").fetchone()[0]
    finally:
        conn.close()

    def boom(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO audit_log "
            "(actor_id, action_type, entity_type, entity_id, created_at) "
            "VALUES ('gone', 'should_rollback', 'meta', 'x', 2)"
        )
        raise RuntimeError("intentional migration failure")

    runner = MigrationRunner(db_path)
    with pytest.raises(MigrationFailedError) as err:
        runner.run([boom])
    assert isinstance(err.value.__cause__, RuntimeError)

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == before
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE action_type='should_rollback'"
            ).fetchone()[0]
            == 0
        )
        assert conn.execute("PRAGMA user_version").fetchone()[0] == user_before
    finally:
        conn.close()


def test_schema_version_too_new_raises(
    initializer: DbInitializer, tmp_path: Path
) -> None:
    db_path = tmp_path / "pipeline.db"
    initializer.init_pipeline(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE meta SET value = '5' WHERE key = 'schema_version'"
        )
        conn.commit()
    finally:
        conn.close()

    runner = MigrationRunner(db_path)
    with pytest.raises(SchemaVersionTooNewError):
        runner.run(["SELECT 1"])


def test_sql_string_migration_telemetry(
    initializer: DbInitializer, tmp_path: Path
) -> None:
    db_path = tmp_path / "telemetry.db"
    initializer.init_telemetry(db_path)

    runner = MigrationRunner(db_path)
    new_v = runner.run(
        [
            "CREATE TABLE migration_probe (id INTEGER PRIMARY KEY);",
        ]
    )
    assert new_v == 1

    conn = sqlite3.connect(db_path)
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert "migration_probe" in names
    finally:
        conn.close()