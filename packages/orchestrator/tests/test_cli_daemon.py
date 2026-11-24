"""Orchestrator CLI & daemon lock invariants (Task 097)."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.cli import (
    MVP_MOTIF_NAMES,
    OrchestratorConfig,
    build_conveyor_plan,
    parse_args,
    resolve_plan_motifs,
    run_cli,
)
from orchestrator.daemon import (
    DaemonLockHeldError,
    DaemonShutdownState,
    acquire_daemon_lock,
    handle_sigterm,
    lock_path_for_db,
    make_sigterm_handler,
    release_daemon_session,
    wal_checkpoint_truncate,
)


def test_parse_cli_flags() -> None:
    cfg = parse_args(
        [
            "--backend",
            "live",
            "--flow-mode",
            "batch-desk",
            "--mvp-slice",
            "--dry-run",
            "--daemon",
            "--db-path",
            "tmp/pipeline.db",
        ]
    )
    assert cfg.backend == "live"
    assert cfg.flow_mode == "batch-desk"
    assert cfg.mvp_slice is True
    assert cfg.dry_run is True
    assert cfg.daemon is True
    assert cfg.db_path == Path("tmp/pipeline.db")


def test_mvp_slice_limits_motifs() -> None:
    assert resolve_plan_motifs(mvp_slice=True) == MVP_MOTIF_NAMES
    plan = build_conveyor_plan(
        OrchestratorConfig(
            backend="stub",
            flow_mode="headless",
            mvp_slice=True,
            dry_run=True,
            daemon=False,
            db_path=Path("pipeline.db"),
        )
    )
    assert plan["motif_components"] == list(MVP_MOTIF_NAMES)


def test_full_plan_includes_extended_catalog() -> None:
    extended = resolve_plan_motifs(mvp_slice=False)
    assert len(extended) > len(MVP_MOTIF_NAMES)
    for motif in MVP_MOTIF_NAMES:
        assert motif in extended


def test_duplicate_lock_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    first = acquire_daemon_lock(db_path)
    assert lock_path_for_db(db_path) == db_path.with_suffix(db_path.suffix + ".lock")
    try:
        with pytest.raises(DaemonLockHeldError):
            acquire_daemon_lock(db_path)
    finally:
        release_daemon_session(first)


def test_sigterm_releases_lock_and_checkpoints(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    session = acquire_daemon_lock(db_path)
    assert session._advisory.held
    state = DaemonShutdownState()
    handler, shared = make_sigterm_handler(session, state=state)
    handler(15, None)
    assert shared.lock_released is True
    assert shared.wal_checkpoint_requested is True
    assert not session._advisory.held
    if session.connection is not None:
        session.connection.close()
        session.connection = None


def test_handle_sigterm_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    session = acquire_daemon_lock(db_path)
    state = DaemonShutdownState()
    handle_sigterm(state, session)
    handle_sigterm(state, session)
    assert state.lock_released is True
    assert state.wal_checkpoint_requested is True
    if session.connection is not None:
        session.connection.close()
        session.connection = None


def test_dry_run_daemon_skips_lock(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cfg = OrchestratorConfig(
        backend="stub",
        flow_mode="headless",
        mvp_slice=False,
        dry_run=True,
        daemon=True,
        db_path=tmp_path / "pipeline.db",
    )
    code, plan = run_cli(cfg)
    assert code == 0
    assert "daemon_lock" not in plan
    captured = capsys.readouterr()
    assert "motif_components" in captured.out


def test_run_cli_acquires_lock_when_daemon(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    cfg = OrchestratorConfig(
        backend="stub",
        flow_mode="headless",
        mvp_slice=True,
        dry_run=False,
        daemon=True,
        db_path=db_path,
    )
    code, plan = run_cli(cfg)
    assert code == 0
    assert plan["daemon_lock"] == str(lock_path_for_db(db_path))
    session = acquire_daemon_lock(db_path)
    release_daemon_session(session)


def test_wal_checkpoint_truncate_on_release(tmp_path: Path) -> None:
    db_path = tmp_path / "pipeline.db"
    session = acquire_daemon_lock(db_path)
    assert session.connection is not None
    session.connection.execute("CREATE TABLE IF NOT EXISTS probe (id INTEGER)")
    session.connection.execute("INSERT INTO probe (id) VALUES (1)")
    session.connection.commit()
    busy, _, _ = wal_checkpoint_truncate(session.connection)
    assert busy in (0, 1)
    release_daemon_session(session)
    assert session.connection is None
    assert not session._advisory.held