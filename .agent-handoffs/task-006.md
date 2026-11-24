# Task 006 — Database migration runner & `VACUUM INTO` backup

## Branch
`task/006-db-migrations-backup`

## Delivered
- `packages/db/src/migrations.py` — `DbInitializer`, `MigrationRunner`, errors
- `packages/db/tests/test_migrations.py` — offline temp-file coverage

## Contracts
| Component | Behavior |
|-----------|----------|
| `DbInitializer` | Executes `schema/pipeline.sql` and `schema/telemetry.sql` from repo root (`schema_dir` override for tests). Pipeline `meta.schema_version` must equal `4`. |
| `MigrationRunner` | Refuses DBs with `meta.schema_version > MAX_SCHEMA_VERSION` (`SchemaVersionTooNewError`). Before steps: `VACUUM INTO` → `{db}.pre-migrate.snapshot`, then `PRAGMA quick_check`. Steps run in a transaction; each success bumps `PRAGMA user_version` by 1. Failure restores snapshot and raises `MigrationFailedError`. |
| `MAX_SCHEMA_VERSION` | `4` |

## Migration tracking
Authoritative schema level remains `meta.schema_version` (pipeline only). Applied migration steps increment `PRAGMA user_version` per step (documented for tests).

## Verify
```bash
uv run pytest packages/db/tests/test_migrations.py
```
or from `packages/db`:
```bash
pytest tests/test_migrations.py
```

## Dependencies
Task 005 `PipelineDb` is **not** in this worktree; implementation uses stdlib `sqlite3` only.