"""tc-conveyor CLI: headless conveyor flags and MVP slice planning (Task 097)."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from orchestrator.daemon import DaemonSession, acquire_daemon_lock, release_daemon_session

BackendMode = Literal["stub", "live"]
FlowMode = Literal["headless", "batch-desk"]

MVP_MOTIF_NAMES: tuple[str, ...] = (
    "StickmanStage",
    "AudioEvidenceCard",
    "RedactedDocReveal",
    "FoiaFootageFrame",
)

FULL_PLAN_MOTIFS: tuple[str, ...] = MVP_MOTIF_NAMES + (
    "TimelineScrubber",
    "AnimatedMapRoute",
    "CellTowerTriangulation",
    "SplitScreenComparison",
    "CaseBoardSpine",
    "QuotePullout",
    "EvidenceGridMatrix",
    "ChapterSlateTransition",
    "Illustrative2KPanZoom",
    "HeroVideoBridge",
)

PROGRAM_NAME = "tc-conveyor"


@dataclass(frozen=True)
class OrchestratorConfig:
    backend: BackendMode
    flow_mode: FlowMode
    mvp_slice: bool
    dry_run: bool
    daemon: bool
    db_path: Path


def default_db_path() -> Path:
    return Path("pipeline.db")


def resolve_plan_motifs(*, mvp_slice: bool) -> tuple[str, ...]:
    if mvp_slice:
        return MVP_MOTIF_NAMES
    return FULL_PLAN_MOTIFS


def build_conveyor_plan(config: OrchestratorConfig) -> dict[str, object]:
    motifs = resolve_plan_motifs(mvp_slice=config.mvp_slice)
    return {
        "program": PROGRAM_NAME,
        "backend": config.backend,
        "flow_mode": config.flow_mode,
        "mvp_slice": config.mvp_slice,
        "dry_run": config.dry_run,
        "daemon": config.daemon,
        "db_path": str(config.db_path),
        "motif_components": list(motifs),
    }


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=PROGRAM_NAME)
    parser.add_argument(
        "--backend",
        choices=("stub", "live"),
        default="stub",
        help="Render/flow backend (stub keeps spend at $0).",
    )
    parser.add_argument(
        "--flow-mode",
        choices=("headless", "batch-desk"),
        default="headless",
        dest="flow_mode",
        help="Headless conveyor default; batch-desk is the optional UI bridge.",
    )
    parser.add_argument(
        "--mvp-slice",
        action="store_true",
        help="Limit the conveyor plan to the authoritative 4-motif Remotion MVP.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only; do not acquire locks or touch pipeline.db.",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Acquire the sole-writer pipeline.db.lock for a headless daemon session.",
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite database path (lock file is <db-path>.lock).",
    )
    return parser


def config_from_namespace(namespace: argparse.Namespace) -> OrchestratorConfig:
    db_path = namespace.db_path if namespace.db_path is not None else default_db_path()
    return OrchestratorConfig(
        backend=namespace.backend,
        flow_mode=namespace.flow_mode,
        mvp_slice=bool(namespace.mvp_slice),
        dry_run=bool(namespace.dry_run),
        daemon=bool(namespace.daemon),
        db_path=Path(db_path),
    )


def parse_args(argv: Sequence[str] | None = None) -> OrchestratorConfig:
    parser = build_argument_parser()
    return config_from_namespace(parser.parse_args(list(argv) if argv is not None else None))


def run_cli(config: OrchestratorConfig) -> tuple[int, dict[str, object]]:
    plan = build_conveyor_plan(config)
    session: DaemonSession | None = None
    try:
        if config.daemon and not config.dry_run:
            session = acquire_daemon_lock(config.db_path)
            plan["daemon_lock"] = str(session.lock_path)
            plan["daemon_pid"] = session.owner_id
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0, plan
    finally:
        if session is not None:
            release_daemon_session(session)


def main(argv: Sequence[str] | None = None) -> int:
    config = parse_args(argv)
    exit_code, _ = run_cli(config)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))