"""Cross-provider USD escrow ledger.

Admission control runs only against ``pipeline.db``. The SQLite triggers
``trg_offline_test_zero_spend_guard`` and ``trg_provider_global_budget_cap_guard``
are the authority for the zero-spend offline-test rule, the monthly caps in
``monthly_budget_ledger``, and the per-episode video cap on
``episodes.video_budget_cap_micro_usd``. This module executes the named
statements in ``schema/queries.sql`` inside ``BEGIN IMMEDIATE`` and surfaces
those trigger aborts as ``BudgetCapExceeded``. It does not re-check those
dollar ceilings in Python.

Act 1 hero allocation is not a trigger predicate (``provider_spend_reservations``
has no ``act_number`` column). When the caller passes ``act_number=1`` for a
FLOW video provider (``gemini_omni`` or ``vertex_veo``, the same set as the
per-episode arm of ``trg_provider_global_budget_cap_guard``) and a billable
purpose (``PRODUCTION`` or ``LIVE_SANDBOX``), the repository rejects the
reservation before insert when the episode's charged FLOW video micro USD plus
the new estimate would exceed 40% of that episode's
``video_budget_cap_micro_usd``. On the schema default of ``10_400_000``
($10.40/ep) that ceiling is ``4_160_000`` micro USD. The comparison uses the
same strict ``>`` and the same charged-status CASE expression as the trigger.
The check runs inside the same ``BEGIN IMMEDIATE`` transaction as the insert.

``flow_backend_mode`` (``GEMINI_OMNI_INTERACTIONS``, ``VERTEX_VEO_ENTERPRISE``,
``HUMAN_BATCH_DESK``) is recorded on the returned reservation and is never a
reason to skip the USD ledger.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

# episodes.flow_backend_mode CHECK in schema/pipeline.sql.
FLOW_BACKEND_MODES = (
    "GEMINI_OMNI_INTERACTIONS",
    "VERTEX_VEO_ENTERPRISE",
    "HUMAN_BATCH_DESK",
)

# Per-episode video arm of trg_provider_global_budget_cap_guard.
FLOW_VIDEO_PROVIDER_IDS = ("gemini_omni", "vertex_veo")

# Purposes that consume monthly and episode caps (trigger WHEN clause).
_BILLABLE_PURPOSES = ("PRODUCTION", "LIVE_SANDBOX")

# Schema default of episodes.video_budget_cap_micro_usd ($10.40/ep).
EPISODE_VIDEO_CAP_MICRO_USD_DEFAULT = 10_400_000
ACT1_HERO_ALLOCATION_NUMERATOR = 40
ACT1_HERO_ALLOCATION_DENOMINATOR = 100

_NAMED_QUERY = re.compile(r"^-- name:\s+(\S+)\s*$", re.MULTILINE)
_REQUIRED_QUERIES = ("reserve_provider_budget", "settle_provider_budget")
_TRIGGER_CODES = (
    "OFFLINE_TEST_ZERO_SPEND",
    "GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED",
)

# Same charged-micro expression as trg_provider_global_budget_cap_guard.
_FLOW_VIDEO_CHARGED_SQL = """
SELECT COALESCE(SUM(
  CASE
    WHEN status = 'COMMITTED' THEN COALESCE(actual_micro_usd, estimated_micro_usd)
    WHEN status IN ('RESERVED', 'UNKNOWN_HOLD') THEN estimated_micro_usd
    ELSE 0
  END
), 0) AS charged_micro_usd
FROM provider_spend_reservations
WHERE episode_id = :episode_id
  AND provider_id IN ('gemini_omni', 'vertex_veo')
"""

_EPISODE_VIDEO_CAP_SQL = """
SELECT video_budget_cap_micro_usd
FROM episodes
WHERE episode_id = :episode_id
"""


class BudgetCapExceeded(Exception):
    """A pipeline.db budget trigger aborted the write, or the Act 1 guard rejected it.

    ``code`` is the trigger token (``OFFLINE_TEST_ZERO_SPEND`` or
    ``GLOBAL_OR_EPISODE_BUDGET_CAP_EXCEEDED``) or ``ACT1_HERO_ALLOCATION_EXCEEDED``.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class ReservationNotOpen(Exception):
    """``settle_provider_budget`` matched no ``RESERVED`` or ``UNKNOWN_HOLD`` row."""


@dataclass(frozen=True)
class ProviderReservation:
    reservation_id: str
    status: str
    estimated_micro_usd: int | None = None
    actual_micro_usd: int | None = None
    flow_backend_mode: str | None = None


def act1_hero_cap_micro_usd(episode_video_cap_micro_usd: int) -> int:
    """40% of the episode video cap, floored to micro USD.

    ``act1_hero_cap_micro_usd(10_400_000) == 4_160_000``.
    """
    if episode_video_cap_micro_usd < 0:
        raise ValueError("episode video cap must be >= 0")
    return (
        episode_video_cap_micro_usd
        * ACT1_HERO_ALLOCATION_NUMERATOR
        // ACT1_HERO_ALLOCATION_DENOMINATOR
    )


def load_named_queries(queries_sql: Path) -> dict[str, str]:
    text = queries_sql.read_text(encoding="utf-8")
    marks = list(_NAMED_QUERY.finditer(text))
    found: dict[str, str] = {}
    for index, mark in enumerate(marks):
        start = mark.end()
        end = marks[index + 1].start() if index + 1 < len(marks) else len(text)
        found[mark.group(1)] = text[start:end].strip()
    missing = [name for name in _REQUIRED_QUERIES if name not in found]
    if missing:
        raise FileNotFoundError(
            f"{queries_sql} is missing named queries: {', '.join(missing)}"
        )
    return found


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "schema" / "queries.sql").is_file():
            return parent
    raise FileNotFoundError("Could not locate schema/queries.sql from escrow_repo.py")


def _budget_code(exc: sqlite3.Error) -> str | None:
    message = str(exc)
    for code in _TRIGGER_CODES:
        if code in message:
            return code
    return None


class GlobalBudgetLedgerRepository:
    """Reserve and settle ``provider_spend_reservations`` on ``pipeline.db``."""

    def __init__(
        self,
        pipeline_db: Path | str,
        *,
        queries_sql: Path | str | None = None,
        busy_timeout_ms: int = 10_000,
    ) -> None:
        self.pipeline_db = Path(pipeline_db)
        queries_path = Path(queries_sql) if queries_sql is not None else _repo_root() / "schema" / "queries.sql"
        self.queries = load_named_queries(queries_path)
        self.busy_timeout_ms = busy_timeout_ms

    def reserve_provider_budget(
        self,
        *,
        reservation_id: str,
        episode_id: str | None,
        job_id: str,
        attempt_number: int,
        provider_id: str,
        purpose: str,
        year_month: str,
        estimated_micro_usd: int,
        now_ms: int,
        flow_backend_mode: str,
        act_number: int | None = None,
    ) -> ProviderReservation:
        """Insert a ``RESERVED`` row via the ``reserve_provider_budget`` statement.

        ``flow_backend_mode`` is passed through onto the result for every mode,
        including ``HUMAN_BATCH_DESK`` and ``VERTEX_VEO_ENTERPRISE``.
        """
        self._require_flow_backend_mode(flow_backend_mode)
        if act_number is not None and act_number not in (1, 2, 3):
            raise ValueError("act_number must be 1, 2, 3, or omitted")

        def body(conn: sqlite3.Connection) -> ProviderReservation:
            if (
                act_number == 1
                and provider_id in FLOW_VIDEO_PROVIDER_IDS
                and purpose in _BILLABLE_PURPOSES
            ):
                self._reject_act1_over_allocation(
                    conn,
                    episode_id=episode_id,
                    estimated_micro_usd=estimated_micro_usd,
                )
            row = conn.execute(
                self.queries["reserve_provider_budget"],
                {
                    "reservation_id": reservation_id,
                    "episode_id": episode_id,
                    "job_id": job_id,
                    "attempt_number": attempt_number,
                    "provider_id": provider_id,
                    "purpose": purpose,
                    "year_month": year_month,
                    "estimated_micro_usd": estimated_micro_usd,
                    "now_ms": now_ms,
                },
            ).fetchone()
            if row is None:
                raise RuntimeError("reserve_provider_budget did not return a row")
            return ProviderReservation(
                reservation_id=row["reservation_id"],
                estimated_micro_usd=row["estimated_micro_usd"],
                status=row["status"],
                flow_backend_mode=flow_backend_mode,
            )

        return self._immediate(body)

    def settle_provider_budget(
        self,
        *,
        reservation_id: str,
        actual_micro_usd: int,
        final_status: str,
        now_ms: int,
    ) -> ProviderReservation:
        """Set ``actual_micro_usd`` and ``status`` via ``settle_provider_budget``."""

        def body(conn: sqlite3.Connection) -> ProviderReservation:
            row = conn.execute(
                self.queries["settle_provider_budget"],
                {
                    "reservation_id": reservation_id,
                    "actual_micro_usd": actual_micro_usd,
                    "final_status": final_status,
                    "now_ms": now_ms,
                },
            ).fetchone()
            if row is None:
                raise ReservationNotOpen(
                    f"reservation {reservation_id} is not RESERVED or UNKNOWN_HOLD"
                )
            return ProviderReservation(
                reservation_id=row["reservation_id"],
                actual_micro_usd=row["actual_micro_usd"],
                status=row["status"],
            )

        return self._immediate(body)

    def _reject_act1_over_allocation(
        self,
        conn: sqlite3.Connection,
        *,
        episode_id: str | None,
        estimated_micro_usd: int,
    ) -> None:
        if episode_id is None:
            raise ValueError("act_number=1 FLOW video reservation requires episode_id")
        cap_row = conn.execute(
            _EPISODE_VIDEO_CAP_SQL, {"episode_id": episode_id}
        ).fetchone()
        if cap_row is None:
            raise ValueError(f"unknown episode_id {episode_id}")
        episode_cap = int(cap_row["video_budget_cap_micro_usd"])
        limit = act1_hero_cap_micro_usd(episode_cap)
        charged = int(
            conn.execute(_FLOW_VIDEO_CHARGED_SQL, {"episode_id": episode_id}).fetchone()[
                "charged_micro_usd"
            ]
        )
        projected = charged + estimated_micro_usd
        if projected > limit:
            raise BudgetCapExceeded(
                (
                    "ACT1_HERO_ALLOCATION_EXCEEDED: Act 1 FLOW video would reach "
                    f"{projected} micro USD, above 40% of the episode video cap "
                    f"({limit} = 0.40 * {episode_cap})"
                ),
                code="ACT1_HERO_ALLOCATION_EXCEEDED",
            )

    def _immediate(self, body):
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            try:
                result = body(conn)
            except sqlite3.Error as exc:
                _rollback(conn)
                code = _budget_code(exc)
                if code is not None:
                    raise BudgetCapExceeded(str(exc), code=code) from exc
                raise
            except Exception:
                _rollback(conn)
                raise
            else:
                try:
                    conn.execute("COMMIT")
                except sqlite3.Error:
                    _rollback(conn)
                    raise
                return result
        finally:
            conn.close()

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

    @staticmethod
    def _require_flow_backend_mode(flow_backend_mode: str) -> None:
        if flow_backend_mode not in FLOW_BACKEND_MODES:
            allowed = ", ".join(FLOW_BACKEND_MODES)
            raise ValueError(
                f"flow_backend_mode must be one of {allowed}, got {flow_backend_mode!r}"
            )


def _rollback(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("ROLLBACK")
    except sqlite3.Error:
        pass
