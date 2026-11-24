"""Flow-job queue and two-strike repository.

Writes go to ``pipeline.db`` inside ``BEGIN IMMEDIATE``. Crash checkpoints
(``SUBMITTING``, ``RUNNING``, ``UNKNOWN_RECONCILE``) and
``provider_operation_id`` are committed before ``record_attempt`` returns, so
a restarted process sees them on the same database file.

Completed attempts insert ``flow_job_attempts``. ``pool_source`` is limited to
``GEMINI_API_USD``, ``VERTEX_USD``, ``DAILY_CREDITS``, and ``MONTHLY_CREDITS``.
A safety block (``total_output_tokens == 0``) settles the matching
``provider_spend_reservations`` row (``job_id`` = ``flow_job_id`` and the same
``attempt_number``, status ``RESERVED`` or ``UNKNOWN_HOLD``) to ``RELEASED``
with ``actual_micro_usd = 0``.

Strike 1 sets ``flow_jobs.state`` to ``STRIKE_1_RETRY_SAFE``. The next attempt
persists ``prompt_used`` from ``flow_jobs.prompt_v2_safe``. Strike 2 sets
``SWITCHED_TO_FALLBACK``. Attempt 3 inserts another ``flow_job_attempts`` row
and is rejected by ``trg_flow_two_strike_breaker`` (``LAW_3_BREAKER``). That
``sqlite3.IntegrityError`` is rolled back and re-raised. It is not swallowed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

POOL_SOURCES = (
    "GEMINI_API_USD",
    "VERTEX_USD",
    "DAILY_CREDITS",
    "MONTHLY_CREDITS",
)

CRASH_STATES = (
    "SUBMITTING",
    "RUNNING",
    "UNKNOWN_RECONCILE",
)

QA_VERDICTS = (
    "PASS",
    "PENDING_MANUAL_SPOT_CHECK",
    "FAIL_SAFETY_BLOCK",
    "FAIL_MORPH",
    "FAIL_DURATION_RES",
    "UNKNOWN_TIMEOUT",
)

_STRIKE_VERDICTS = frozenset(
    {
        "FAIL_SAFETY_BLOCK",
        "FAIL_MORPH",
        "FAIL_DURATION_RES",
        "UNKNOWN_TIMEOUT",
    }
)

_OPEN_RESERVATION_STATUSES = ("RESERVED", "UNKNOWN_HOLD")


class FlowJobNotFound(LookupError):
    """``flow_jobs`` has no row for the given ``flow_job_id``."""


@dataclass(frozen=True)
class FlowAttemptResult:
    flow_job_id: str
    state: str
    attempts_used: int
    provider_operation_id: str | None
    attempt_id: str | None = None
    attempt_number: int | None = None
    prompt_used: str | None = None
    retry_prompt: str | None = None
    pool_source: str | None = None
    qa_verdict: str | None = None
    reservation_id: str | None = None
    reservation_status: str | None = None
    actual_micro_usd: int | None = None


class FlowJobRepository:
    """Persist flow-job crash checkpoints and at most two attempts."""

    def __init__(self, pipeline_db: str, *, busy_timeout_ms: int = 5_000) -> None:
        if isinstance(busy_timeout_ms, bool) or not isinstance(busy_timeout_ms, int):
            raise ValueError("busy_timeout_ms must be an int")
        if busy_timeout_ms < 0:
            raise ValueError("busy_timeout_ms must be >= 0")
        self.pipeline_db = str(pipeline_db)
        self.busy_timeout_ms = busy_timeout_ms

    def record_attempt(
        self,
        *,
        flow_job_id: str,
        now_ms: int,
        provider_operation_id: str | None = None,
        state: str | None = None,
        attempt_id: str | None = None,
        pool_source: str | None = None,
        qa_verdict: str | None = None,
        total_output_tokens: int | None = None,
        prompt_used: str | None = None,
        cost_micro_usd: int = 0,
        credits_charged: int = 0,
        qa_notes: str | None = None,
    ) -> FlowAttemptResult:
        """Record a crash checkpoint or one completed attempt.

        A crash checkpoint is ``state`` in ``SUBMITTING``, ``RUNNING``, or
        ``UNKNOWN_RECONCILE`` with no attempt payload. ``UNKNOWN_RECONCILE``
        also moves matching ``RESERVED`` spend rows to ``UNKNOWN_HOLD``.

        A completed attempt requires ``attempt_id``, ``pool_source``, and
        ``qa_verdict``. ``total_output_tokens == 0`` is a safety block: the
        attempt is stored as ``FAIL_SAFETY_BLOCK`` with zero cost and the
        matching reservation is released at ``$0``.
        """
        _require_text("flow_job_id", flow_job_id)
        _require_int("now_ms", now_ms, minimum=0)
        if provider_operation_id is not None:
            _require_text("provider_operation_id", provider_operation_id)

        completed = any(
            value is not None
            for value in (attempt_id, pool_source, qa_verdict, total_output_tokens, prompt_used)
        )
        if state is not None and completed:
            raise ValueError("pass either a crash state or an attempt payload, not both")
        if state is not None:
            if state not in CRASH_STATES:
                allowed = ", ".join(CRASH_STATES)
                raise ValueError(f"crash state must be one of {allowed}, got {state!r}")
            return self._checkpoint(
                flow_job_id=flow_job_id,
                now_ms=now_ms,
                state=state,
                provider_operation_id=provider_operation_id,
            )
        if not completed:
            raise ValueError("record_attempt requires a crash state or an attempt payload")

        _require_text("attempt_id", attempt_id)
        if pool_source not in POOL_SOURCES:
            allowed = ", ".join(POOL_SOURCES)
            raise ValueError(f"pool_source must be one of {allowed}, got {pool_source!r}")
        _require_int("cost_micro_usd", cost_micro_usd, minimum=0)
        _require_int("credits_charged", credits_charged, minimum=0)
        if total_output_tokens is not None:
            _require_int("total_output_tokens", total_output_tokens, minimum=0)
        if prompt_used is not None:
            _require_text("prompt_used", prompt_used)

        safety_block = total_output_tokens == 0
        verdict = qa_verdict
        if safety_block and verdict not in _STRIKE_VERDICTS:
            verdict = "FAIL_SAFETY_BLOCK"
        if verdict not in QA_VERDICTS:
            allowed = ", ".join(QA_VERDICTS)
            raise ValueError(f"qa_verdict must be one of {allowed}, got {verdict!r}")
        if safety_block:
            cost_micro_usd = 0
            credits_charged = 0

        return self._record_completed(
            flow_job_id=flow_job_id,
            now_ms=now_ms,
            provider_operation_id=provider_operation_id,
            attempt_id=attempt_id,
            pool_source=pool_source,
            qa_verdict=verdict,
            prompt_used=prompt_used,
            cost_micro_usd=cost_micro_usd,
            credits_charged=credits_charged,
            qa_notes=qa_notes,
            safety_block=safety_block,
        )

    def _checkpoint(
        self,
        *,
        flow_job_id: str,
        now_ms: int,
        state: str,
        provider_operation_id: str | None,
    ) -> FlowAttemptResult:
        with self._transaction() as conn:
            job = _lock_job(conn, flow_job_id)
            if _is_terminal(conn, job["state"]):
                raise ValueError(
                    f"flow job {flow_job_id} is terminal ({job['state']}); "
                    "refusing crash checkpoint"
                )
            conn.execute(
                """
                UPDATE flow_jobs
                SET state = :state,
                    provider_operation_id = CASE
                      WHEN :provider_operation_id IS NULL THEN provider_operation_id
                      ELSE :provider_operation_id
                    END,
                    updated_at = :now_ms
                WHERE flow_job_id = :flow_job_id
                """,
                {
                    "state": state,
                    "provider_operation_id": provider_operation_id,
                    "now_ms": now_ms,
                    "flow_job_id": flow_job_id,
                },
            )
            if state == "UNKNOWN_RECONCILE":
                conn.execute(
                    """
                    UPDATE provider_spend_reservations
                    SET status = 'UNKNOWN_HOLD'
                    WHERE job_id = :flow_job_id
                      AND status = 'RESERVED'
                    """,
                    {"flow_job_id": flow_job_id},
                )
            stored = _lock_job(conn, flow_job_id)
            return _result_from_job(stored)

    def _record_completed(
        self,
        *,
        flow_job_id: str,
        now_ms: int,
        provider_operation_id: str | None,
        attempt_id: str,
        pool_source: str,
        qa_verdict: str,
        prompt_used: str | None,
        cost_micro_usd: int,
        credits_charged: int,
        qa_notes: str | None,
        safety_block: bool,
    ) -> FlowAttemptResult:
        with self._transaction() as conn:
            job = _lock_job(conn, flow_job_id)
            attempt_number = int(job["attempts_used"]) + 1
            chosen_prompt = _prompt_for_attempt(job, attempt_number, prompt_used)
            # Insert first. When attempts_used >= 2, trg_flow_two_strike_breaker
            # aborts this statement with LAW_3_BREAKER. Do not catch that here.
            conn.execute(
                """
                INSERT INTO flow_job_attempts (
                  attempt_id, flow_job_id, attempt_number, provider_operation_id,
                  prompt_used, cost_micro_usd, credits_charged, pool_source,
                  qa_verdict, qa_notes, created_at
                ) VALUES (
                  :attempt_id, :flow_job_id, :attempt_number, :provider_operation_id,
                  :prompt_used, :cost_micro_usd, :credits_charged, :pool_source,
                  :qa_verdict, :qa_notes, :now_ms
                )
                """,
                {
                    "attempt_id": attempt_id,
                    "flow_job_id": flow_job_id,
                    "attempt_number": attempt_number,
                    "provider_operation_id": provider_operation_id,
                    "prompt_used": chosen_prompt,
                    "cost_micro_usd": cost_micro_usd,
                    "credits_charged": credits_charged,
                    "pool_source": pool_source,
                    "qa_verdict": qa_verdict,
                    "qa_notes": qa_notes,
                    "now_ms": now_ms,
                },
            )
            reservation = None
            if safety_block:
                reservation = conn.execute(
                    """
                    UPDATE provider_spend_reservations
                    SET actual_micro_usd = 0,
                        status = 'RELEASED',
                        settled_at = :now_ms
                    WHERE job_id = :flow_job_id
                      AND attempt_number = :attempt_number
                      AND status IN ('RESERVED', 'UNKNOWN_HOLD')
                    RETURNING reservation_id, actual_micro_usd, status
                    """,
                    {
                        "now_ms": now_ms,
                        "flow_job_id": flow_job_id,
                        "attempt_number": attempt_number,
                    },
                ).fetchone()
            new_state = _next_state(qa_verdict, attempt_number)
            conn.execute(
                """
                UPDATE flow_jobs
                SET attempts_used = :attempt_number,
                    state = :state,
                    provider_operation_id = CASE
                      WHEN :provider_operation_id IS NULL THEN provider_operation_id
                      ELSE :provider_operation_id
                    END,
                    updated_at = :now_ms
                WHERE flow_job_id = :flow_job_id
                """,
                {
                    "attempt_number": attempt_number,
                    "state": new_state,
                    "provider_operation_id": provider_operation_id,
                    "now_ms": now_ms,
                    "flow_job_id": flow_job_id,
                },
            )
            stored = _lock_job(conn, flow_job_id)
            retry_prompt = stored["prompt_v2_safe"] if new_state == "STRIKE_1_RETRY_SAFE" else None
            return FlowAttemptResult(
                flow_job_id=stored["flow_job_id"],
                state=stored["state"],
                attempts_used=int(stored["attempts_used"]),
                provider_operation_id=stored["provider_operation_id"],
                attempt_id=attempt_id,
                attempt_number=attempt_number,
                prompt_used=chosen_prompt,
                retry_prompt=retry_prompt,
                pool_source=pool_source,
                qa_verdict=qa_verdict,
                reservation_id=None if reservation is None else reservation["reservation_id"],
                reservation_status=None if reservation is None else reservation["status"],
                actual_micro_usd=None if reservation is None else int(reservation["actual_micro_usd"]),
            )

    def _transaction(self):
        return _ImmediateTransaction(self._connect())

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.pipeline_db,
            isolation_level=None,
            timeout=self.busy_timeout_ms / 1000,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {int(self.busy_timeout_ms)}")
        conn.execute("PRAGMA journal_mode = WAL").fetchall()
        conn.execute("PRAGMA synchronous = FULL")
        return conn


class _ImmediateTransaction:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self._conn.execute("BEGIN IMMEDIATE")
        return self._conn

    def __exit__(self, exc_type, exc, tb) -> bool:
        try:
            if exc_type is None:
                try:
                    self._conn.execute("COMMIT")
                except sqlite3.Error:
                    _rollback(self._conn)
                    raise
            else:
                # Includes trg_flow_two_strike_breaker IntegrityError. Roll back
                # and let the original error propagate. Do not swallow it.
                _rollback(self._conn)
        finally:
            self._conn.close()
        return False


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _require_text(name: str, value: str | None) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_int(name: str, value: int, *, minimum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")


def _lock_job(conn: sqlite3.Connection, flow_job_id: str) -> sqlite3.Row:
    row = conn.execute(
        """
        SELECT flow_job_id, episode_id, scene_id, prompt_v1, prompt_v2_safe,
               provider_operation_id, attempts_used, state
        FROM flow_jobs
        WHERE flow_job_id = :flow_job_id
        """,
        {"flow_job_id": flow_job_id},
    ).fetchone()
    if row is None:
        raise FlowJobNotFound(f"unknown flow_job_id {flow_job_id}")
    return row


def _is_terminal(conn: sqlite3.Connection, state: str) -> bool:
    row = conn.execute(
        "SELECT is_terminal FROM flow_job_states WHERE state = :state",
        {"state": state},
    ).fetchone()
    return row is not None and int(row["is_terminal"]) == 1


def _prompt_for_attempt(job: sqlite3.Row, attempt_number: int, prompt_used: str | None) -> str:
    if attempt_number == 1:
        chosen = job["prompt_v1"] if prompt_used is None else prompt_used
    else:
        # Strike 1 retry (and the attempt-3 insert the trigger rejects) uses
        # the safe prompt stored on the job. Caller text cannot replace it.
        chosen = job["prompt_v2_safe"]
    if not chosen:
        raise ValueError("prompt_used is empty")
    return chosen


def _next_state(qa_verdict: str, attempt_number: int) -> str:
    if qa_verdict == "PASS":
        return "ACCEPTED"
    if qa_verdict == "PENDING_MANUAL_SPOT_CHECK":
        return "PENDING_MANUAL_SPOT_CHECK"
    if qa_verdict in _STRIKE_VERDICTS:
        if attempt_number <= 1:
            return "STRIKE_1_RETRY_SAFE"
        return "SWITCHED_TO_FALLBACK"
    raise ValueError(f"unsupported qa_verdict {qa_verdict!r}")


def _result_from_job(job: sqlite3.Row) -> FlowAttemptResult:
    return FlowAttemptResult(
        flow_job_id=job["flow_job_id"],
        state=job["state"],
        attempts_used=int(job["attempts_used"]),
        provider_operation_id=job["provider_operation_id"],
    )
