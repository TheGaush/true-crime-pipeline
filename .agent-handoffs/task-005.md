# Task 005 handoff — Python sole-writer SQLite WAL driver

TC-Task-ID: 005
TC-Track: Part 1
TC-Never-Merge: true
Branch: `task/005-db-wal-sole-writer`

## Result

`PipelineDb` in `packages/db` is the sole writer for one SQLite file.

- Pragmas on every open: `journal_mode=WAL`, `synchronous=FULL`, `foreign_keys=ON`, `busy_timeout=5000`.
- Writes use `BEGIN IMMEDIATE` inside a `threading.RLock`. Reads use a short `BEGIN DEFERRED`. Both context managers close their cursor. `with PipelineDb(...)` closes cursors, the connection, and the advisory lock.
- `SQLITE_BUSY` (including extended codes whose low byte is busy) and `OSError` errno `EBUSY` retry with bounded jitter (`base * 2**n`, capped, then `uniform(0.5, 1.0)`).
- Startup asserts a version tuple `>= (3, 51, 3)`. Omit `sqlite_version` in production so the check reads `sqlite3.sqlite_version_info`. Passing `sqlite_version` does not skip the comparison; it is the tuple that is compared. This host's linked SQLite is **3.49.1**, so `PipelineDb(path)` with no injected tuple raises `SqliteVersionError`. Tests inject `(3, 51, 3)` and also monkeypatch `sqlite3.sqlite_version_info` for the default path.
- UNC paths (`\\` or `//`) are rejected before any filesystem or network call. `path_classifier` can classify an otherwise local path as `smb`, `nfs`, `unc`, or `network`. Only the class `local` is accepted. Drive-letter shares are not probed (that can touch the network).
- If `audit_log` has the v4 columns, startup inserts one `sqlite_runtime_started` row whose `detail_json.sqlite_version` is the linked library string. A blank file does not create that table and does not insert. The full schema is not copied into this package; pass it as `schema_sql` (tests read `schema/pipeline.sql` when it is in the worktree).
- Sole writer: OS advisory lock at `{db_path}.lock` (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere; stdlib only, no portalocker) plus `meta.sole_writer_owner` heartbeat JSON (`owner_id`, `pid`, `hostname`, `heartbeat_unix_ms`) when `meta` exists. A second `PipelineDb` on the same path fails with `SoleWriterOccupiedError`. `refresh_owner_heartbeat()` updates the row. `checkpoint_passive()` and `checkpoint_truncate()` run `PRAGMA wal_checkpoint` outside a user transaction.

## Import

`pyproject.toml` maps package `db` onto `packages/db/src` (no runtime dependencies; pytest is an optional dev extra). Tests load that package from `src/__init__.py`, which re-exports `PipelineDb`.

```python
from db import PipelineDb

with PipelineDb(path, schema_sql=open("schema/pipeline.sql", encoding="utf-8").read()) as db:
    db.execute("SELECT value FROM meta WHERE key = ?", ("schema_version",))
    db.checkpoint_truncate()
```

Production callers must not pass `sqlite_version`. On this machine that means the process needs SQLite >= 3.51.3 or startup fails on purpose.

## Tests

`python -m pytest -p no:cacheprovider -q packages/db/tests/test_connection.py`

33 passed in 7.82s on this host (SQLite 3.49.1). WAL opened on the local temp directory, so the 16-thread stress test ran (16 threads × 20 inserts, 0 unhandled `SQLITE_BUSY`). If WAL cannot be enabled, that test skips with `host SQLite cannot open WAL` and the retry, path, and advisory-lock tests still run.

Cross-process coverage is a subprocess holder (`test_second_process_cannot_become_writer`), not only threads. Threads prove the RLock (`max` concurrent writers is 1). A second handle on the lock file is also tested without opening SQLite.

## Owned files

- `packages/db/src/connection.py`
- `packages/db/src/__init__.py`
- `packages/db/pyproject.toml`
- `packages/db/tests/test_connection.py`
- `.agent-handoffs/task-005.md`

No new runtime dependency. Schema SQL was not edited.
