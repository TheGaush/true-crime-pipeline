"""True-crime pipeline orchestrator (CLI & headless conveyor daemon)."""

from orchestrator.cli import PROGRAM_NAME, OrchestratorConfig, build_conveyor_plan, parse_args
from orchestrator.daemon import DaemonLockHeldError, DaemonSession, acquire_daemon_lock

__all__ = [
    "PROGRAM_NAME",
    "OrchestratorConfig",
    "DaemonLockHeldError",
    "DaemonSession",
    "acquire_daemon_lock",
    "build_conveyor_plan",
    "parse_args",
]