"""Legal conveyor steps and a three-slot oldest-first Flow batch queue.

The forward path is the contiguous ``episode_states.seq_order`` prefix in
``schema/pipeline.sql`` (``QUEUED`` through ``PUBLISHED``). Side states stay
in the schema for triggers; this repository does not move an episode onto them.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

AWAITING_FLOW_BATCH = "AWAITING_FLOW_BATCH"
FLOW_BATCH_SLOT_CAP = 3
ADVANCED = "ADVANCED"
BACKPRESSURE_QUEUE_FULL = "BACKPRESSURE_QUEUE_FULL"


class EpisodeNotFound(Exception):
    """Raised when ``episode_id`` is not in ``episodes``."""

    def __init__(self, episode_id: str) -> None:
        self.episode_id = episode_id
        super().__init__(f"episode not found: {episode_id}")


class IllegalTransition(Exception):
    """Raised for a skip, a backward move, or any state off the legal path.

    The episode row is left unchanged.
    """

    def __init__(self, episode_id: str, from_state: str, to_state: str, reason: str) -> None:
        self.episode_id = episode_id
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        super().__init__(
            f"ILLEGAL_TRANSITION: {episode_id} cannot move {from_state} -> {to_state} ({reason})"
        )


@dataclass(frozen=True)
class TransitionResult:
    """Outcome of one ``transition`` call.

    ``status`` is ``ADVANCED`` or ``BACKPRESSURE_QUEUE_FULL``. On backpressure
    ``state`` is the state the episode already had, and ``updated_at`` is None
    because the row was not written.
    """

    episode_id: str
    from_state: str
    requested_state: str
    state: str
    status: str
    updated_at: int | None


@dataclass(frozen=True)
class AwaitingFlowEpisode:
    """One episode parked in ``AWAITING_FLOW_BATCH``."""

    episode_id: str
    created_at: int


def _load_legal_forward_path(connection: sqlite3.Connection) -> tuple[str, ...]:
    """Contiguous ``seq_order`` prefix starting at 1, stopping at the first gap.

    ``QUARANTINED_LEGAL_HOLD`` and the terminal side states sit at seq 89+ and
    are not part of this path.
    """
    try:
        rows = connection.execute(
            "SELECT state, seq_order FROM episode_states ORDER BY seq_order ASC"
        ).fetchall()
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "episode_states is missing; initialize the connection from schema/pipeline.sql"
        ) from exc
    path: list[str] = []
    expected = 1
    for row in rows:
        seq_order = int(row["seq_order"])
        if seq_order != expected:
            break
        path.append(str(row["state"]))
        expected += 1
    if AWAITING_FLOW_BATCH not in path or len(path) < 2:
        raise RuntimeError(
            "episode_states has no contiguous legal path through AWAITING_FLOW_BATCH; "
            f"loaded {path!r}"
        )
    return tuple(path)


class ConveyorStateRepository:
    """SQLite writer for adjacent conveyor steps and the Flow batch cap.

    ``now`` is injected and is called only when a move is committed. It must
    return an integer epoch-millisecond timestamp. The repository does not
    sleep and does not open a network connection.
    """

    def __init__(self, connection: sqlite3.Connection, *, now: Callable[[], int]) -> None:
        if not isinstance(connection, sqlite3.Connection):
            raise TypeError("connection must be a sqlite3.Connection")
        if not callable(now):
            raise TypeError("now must be a callable returning integer epoch milliseconds")
        self._conn = connection
        self._now = now
        # Own BEGIN IMMEDIATE / COMMIT so the slot count and the update share one transaction.
        self._conn.isolation_level = None
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        self._path = _load_legal_forward_path(self._conn)
        self._index = {state: index for index, state in enumerate(self._path)}

    @property
    def legal_path(self) -> tuple[str, ...]:
        """Legal forward states in ``seq_order``, from the loaded schema."""
        return self._path

    def get_state(self, episode_id: str) -> str:
        row = self._conn.execute(
            "SELECT state FROM episodes WHERE episode_id = ?",
            (episode_id,),
        ).fetchone()
        if row is None:
            raise EpisodeNotFound(episode_id)
        return str(row["state"])

    def transition(self, episode_id: str, to_state: str) -> TransitionResult:
        """Advance one step, or return ``BACKPRESSURE_QUEUE_FULL`` without writing.

        Skips, backward moves, and states outside the legal path raise
        ``IllegalTransition`` and leave the row unchanged. A fourth episode
        that would enter ``AWAITING_FLOW_BATCH`` while three are already parked
        stays in its current state.
        """
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT state FROM episodes WHERE episode_id = ?",
                (episode_id,),
            ).fetchone()
            if row is None:
                raise EpisodeNotFound(episode_id)
            current = str(row["state"])
            self._require_next(episode_id, current, to_state)
            if to_state == AWAITING_FLOW_BATCH and self._awaiting_count() >= FLOW_BATCH_SLOT_CAP:
                self._conn.execute("ROLLBACK")
                return TransitionResult(
                    episode_id=episode_id,
                    from_state=current,
                    requested_state=to_state,
                    state=current,
                    status=BACKPRESSURE_QUEUE_FULL,
                    updated_at=None,
                )
            stamp = self._timestamp()
            self._conn.execute(
                """
                UPDATE episodes
                SET state = ?, updated_at = ?
                WHERE episode_id = ? AND state = ?
                """,
                (to_state, stamp, episode_id, current),
            )
            changed = self._conn.execute("SELECT changes()").fetchone()
            if changed is None or int(changed[0]) != 1:
                raise RuntimeError(
                    f"episode {episode_id} did not advance {current} -> {to_state}"
                )
            self._conn.execute("COMMIT")
        except Exception:
            self._rollback()
            raise
        return TransitionResult(
            episode_id=episode_id,
            from_state=current,
            requested_state=to_state,
            state=to_state,
            status=ADVANCED,
            updated_at=stamp,
        )

    def list_awaiting_flow_batch(self) -> tuple[AwaitingFlowEpisode, ...]:
        """Episodes in ``AWAITING_FLOW_BATCH``, oldest ``created_at`` first.

        Equal timestamps break ties by ``episode_id`` ascending.
        """
        rows = self._conn.execute(
            """
            SELECT episode_id, created_at
            FROM episodes
            WHERE state = ?
            ORDER BY created_at ASC, episode_id ASC
            """,
            (AWAITING_FLOW_BATCH,),
        ).fetchall()
        return tuple(
            AwaitingFlowEpisode(
                episode_id=str(row["episode_id"]),
                created_at=int(row["created_at"]),
            )
            for row in rows
        )

    def _awaiting_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS slot_count FROM episodes WHERE state = ?",
            (AWAITING_FLOW_BATCH,),
        ).fetchone()
        if row is None:
            return 0
        return int(row["slot_count"])

    def _timestamp(self) -> int:
        value = self._now()
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("now() must return an int epoch-millisecond timestamp")
        return value

    def _require_next(self, episode_id: str, current: str, to_state: str) -> None:
        current_index = self._index.get(current)
        if current_index is None:
            raise IllegalTransition(
                episode_id, current, to_state, "off the legal forward path"
            )
        if current_index + 1 >= len(self._path):
            raise IllegalTransition(episode_id, current, to_state, "terminal state")
        expected = self._path[current_index + 1]
        if to_state == expected:
            return
        target_index = self._index.get(to_state)
        if target_index is None:
            reason = "not a legal conveyor state"
        elif target_index < current_index:
            reason = "backward move"
        elif target_index == current_index:
            reason = "same state is not a forward move"
        else:
            reason = "skip"
        raise IllegalTransition(episode_id, current, to_state, reason)

    def _rollback(self) -> None:
        try:
            self._conn.execute("ROLLBACK")
        except sqlite3.OperationalError as exc:
            if "no transaction" not in str(exc).lower():
                raise
