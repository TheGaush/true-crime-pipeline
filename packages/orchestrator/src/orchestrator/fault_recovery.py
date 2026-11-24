"""Offline Part 1 fault-recovery primitives (in-memory + pipeline.db helpers).

No live provider APIs. Recovery behavior mirrors ``flow-hybrid-and-batch-desk.md``
(F-03, F-10, F-18, F-20) and Task 031 saturation re-check rules.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

CRASH_ELIGIBLE = frozenset({"SUBMITTING", "RUNNING"})
UNKNOWN_RECONCILE = "UNKNOWN_RECONCILE"
EVIDENCE_AND_2K_LOCKED = "EVIDENCE_AND_2K_LOCKED"
ABORTED_COPYCAT_WAVE = "ABORTED_COPYCAT_WAVE"
DECISION_FINISH = "FINISH"

WAVE_ABORT_ABOVE = 3
SUNK_COST_SPENT_ABOVE = 0.50
SUNK_COST_WAVE_AT_MOST = 5

_NAMED_QUERY = re.compile(r"^-- name:\s+(\S+)\s*$", re.MULTILINE)


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "schema" / "pipeline.sql").is_file():
            return parent
    raise FileNotFoundError("Could not locate schema/pipeline.sql from fault_recovery")


def extract_query(name: str, *, queries_sql: Path | None = None) -> str:
    path = queries_sql if queries_sql is not None else repo_root() / "schema" / "queries.sql"
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"-- name: {re.escape(name)}\r?\n([\s\S]*?)(?=\r?\n-- name:|$)",
        text,
    )
    if not match:
        raise LookupError(f"Query {name!r} not found in {path}")
    return match.group(1).strip()


def open_pipeline_memory() -> sqlite3.Connection:
    """Load v4 ``pipeline.sql`` into an in-memory database."""
    script = (repo_root() / "schema" / "pipeline.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(":memory:", isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(script)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def mark_unknown_reconcile_on_crash(
    conn: sqlite3.Connection,
    *,
    flow_job_id: str,
    now_ms: int,
) -> None:
    """Mid-flight crash: ``SUBMITTING``/``RUNNING`` -> ``UNKNOWN_RECONCILE`` + ``UNKNOWN_HOLD``."""

    row = conn.execute(
        "SELECT state FROM flow_jobs WHERE flow_job_id = ?",
        (flow_job_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f"unknown flow_job_id {flow_job_id!r}")
    state = str(row["state"])
    if state not in CRASH_ELIGIBLE:
        raise ValueError(
            f"refusing crash reconcile from state {state!r}; "
            f"eligible={sorted(CRASH_ELIGIBLE)}"
        )
    conn.execute(
        "UPDATE flow_jobs SET state = ?, updated_at = ? WHERE flow_job_id = ?",
        (UNKNOWN_RECONCILE, now_ms, flow_job_id),
    )
    conn.execute(
        """
        UPDATE provider_spend_reservations
        SET status = 'UNKNOWN_HOLD'
        WHERE job_id = ?
          AND status = 'RESERVED'
        """,
        (flow_job_id,),
    )


def startup_reconcile_inflight(conn: sqlite3.Connection, *, now_ms: int) -> list[str]:
    """Startup recovery for jobs still in flight (F-10)."""

    rows = conn.execute(extract_query("reconcile_unknown_flow_jobs")).fetchall()
    reconciled: list[str] = []
    for row in rows:
        if str(row["state"]) in CRASH_ELIGIBLE:
            mark_unknown_reconcile_on_crash(
                conn, flow_job_id=str(row["flow_job_id"]), now_ms=now_ms
            )
            reconciled.append(str(row["flow_job_id"]))
    return reconciled


def count_flow_jobs_for_scene(
    conn: sqlite3.Connection, *, episode_id: str, scene_id: str
) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM flow_jobs WHERE episode_id = ? AND scene_id = ?",
        (episode_id, scene_id),
    ).fetchone()
    return int(row["c"])


def settle_unknown_reconciled_job(
    conn: sqlite3.Connection,
    *,
    flow_job_id: str,
    reservation_id: str,
    final_status: str,
    actual_micro_usd: int,
    now_ms: int,
) -> None:
    """After provider poll, settle budget before any retry with the same scene slot."""

    conn.execute(
        """
        UPDATE flow_jobs
        SET state = 'ACCEPTED',
            updated_at = :now_ms
        WHERE flow_job_id = :flow_job_id
          AND state = :reconcile
        """,
        {
            "now_ms": now_ms,
            "flow_job_id": flow_job_id,
            "reconcile": UNKNOWN_RECONCILE,
        },
    )
    conn.execute(
        extract_query("settle_provider_budget"),
        {
            "reservation_id": reservation_id,
            "actual_micro_usd": actual_micro_usd,
            "final_status": final_status,
            "now_ms": now_ms,
        },
    )


def purge_expired_youtube_fields(conn: sqlite3.Connection, *, now_ms: int) -> int:
    """Run ``purge_expired_yt_api_records``; return rows touched."""

    before = conn.total_changes
    conn.execute(extract_query("purge_expired_yt_api_records"), {"now_ms": now_ms})
    return conn.total_changes - before


def decide_pre_shift(
    *,
    n_14d_wave: int,
    has_90d_200k_kill: int,
    tier1_giant_hit: int,
    spent_credits_pct: float,
) -> tuple[str, int, int]:
    """Return ``(decision, sunk_cost_override, aborted)`` (Task 031 / 096 parity)."""

    threat = n_14d_wave > WAVE_ABORT_ABOVE or has_90d_200k_kill == 1
    sunk_cost = (
        spent_credits_pct > SUNK_COST_SPENT_ABOVE
        and n_14d_wave <= SUNK_COST_WAVE_AT_MOST
        and tier1_giant_hit == 0
    )
    if threat and sunk_cost:
        return DECISION_FINISH, 1, 0
    if threat:
        return ABORTED_COPYCAT_WAVE, 0, 1
    return DECISION_FINISH, 0, 0


def evaluate_day2_wave_abort(
    *,
    batch_day: int,
    n_14d_wave: int,
    spent_credits_pct: float,
    has_90d_200k_kill: int = 0,
    tier1_giant_hit: int = 0,
) -> tuple[str, int]:
    """Per-shift re-check on Day 2+; returns ``(decision, aborted)``."""

    if batch_day < 2:
        return DECISION_FINISH, 0
    decision, _override, aborted = decide_pre_shift(
        n_14d_wave=n_14d_wave,
        has_90d_200k_kill=has_90d_200k_kill,
        tier1_giant_hit=tier1_giant_hit,
        spent_credits_pct=spent_credits_pct,
    )
    return decision, aborted


@dataclass(frozen=True, slots=True)
class DispatchRetryTrace:
    idempotency_key: str
    http_statuses: tuple[int, ...]
    backoff_ms: tuple[int, ...]
    retry_count: int
    paid_dispatch_count: int


@dataclass
class InMemory429Dispatcher:
    """Simulate provider ``429`` with bounded backoff; one idempotency key per scene."""

    retry_after_ms: int = 500
    fail_before_success: int = 1
    idempotency_keys_used: list[str] = field(default_factory=list)
    backoff_schedule_ms: list[int] = field(default_factory=list)
    paid_dispatches: int = 0

    def dispatch_with_backoff(
        self,
        *,
        idempotency_key: str,
        http_statuses: Sequence[int] | None = None,
    ) -> DispatchRetryTrace:
        statuses = (
            tuple(http_statuses)
            if http_statuses is not None
            else (429,) * self.fail_before_success + (200,)
        )
        backoffs: list[int] = []
        paid = 0
        for index, status in enumerate(statuses):
            self.idempotency_keys_used.append(idempotency_key)
            if status == 429:
                backoffs.append(self.retry_after_ms)
                self.backoff_schedule_ms.append(self.retry_after_ms)
                continue
            if status == 200:
                paid += 1
                self.paid_dispatches += 1
                break
            raise ValueError(f"unsupported simulated status {status}")
        else:
            raise RuntimeError("dispatch ended without a 200 response")

        retry_count = sum(1 for code in statuses if code == 429)
        return DispatchRetryTrace(
            idempotency_key=idempotency_key,
            http_statuses=statuses,
            backoff_ms=tuple(backoffs),
            retry_count=retry_count,
            paid_dispatch_count=paid,
        )


@dataclass(frozen=True, slots=True)
class Part1StillCheckpoint:
    episode_id: str
    pipeline_state: str
    anchor_lock_status: str
    still_2k_id: str | None
    still_sha256: str | None
    still_generation_count: int = 0


def lock_early_2k_anchor(
    checkpoint: Part1StillCheckpoint,
    *,
    still_2k_id: str,
    still_sha256: str,
) -> Part1StillCheckpoint:
    return Part1StillCheckpoint(
        episode_id=checkpoint.episode_id,
        pipeline_state=EVIDENCE_AND_2K_LOCKED,
        anchor_lock_status="LOCKED",
        still_2k_id=still_2k_id,
        still_sha256=still_sha256,
        still_generation_count=checkpoint.still_generation_count,
    )


def recover_after_anchor_lock_crash(
    checkpoint: Part1StillCheckpoint,
) -> Part1StillCheckpoint:
    """Resume at ``EVIDENCE_AND_2K_LOCKED`` without regenerating the still."""

    if checkpoint.anchor_lock_status != "LOCKED":
        raise ValueError("anchor must be LOCKED before scripting-phase crash recovery")
    if checkpoint.still_sha256 is None:
        raise ValueError("still_sha256 required for idempotent 2K resume")
    return Part1StillCheckpoint(
        episode_id=checkpoint.episode_id,
        pipeline_state=EVIDENCE_AND_2K_LOCKED,
        anchor_lock_status="LOCKED",
        still_2k_id=checkpoint.still_2k_id,
        still_sha256=checkpoint.still_sha256,
        still_generation_count=checkpoint.still_generation_count,
    )