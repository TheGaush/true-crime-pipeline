"""Headless-default conveyor scheduler with optional Batch Desk parking.

``GEMINI_OMNI_INTERACTIONS`` (and ``VERTEX_VEO_ENTERPRISE``) walk the forward
path through ``SCENE_PLAN_APPROVED``, ``VOICE_READY``, and ``ANIMATIC_APPROVED``
to ``MASTERED`` without a human wait, bypassing ``AWAITING_FLOW_BATCH``.

``HUMAN_BATCH_DESK`` parks at most three episodes in ``AWAITING_FLOW_BATCH``
(oldest ``created_at`` first). A fourth legal park attempt returns
``BACKPRESSURE_QUEUE_FULL`` without moving the episode. Upstream scouting
(``QUEUED`` -> ``SCOUTED``) is never blocked by a full batch queue.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

FlowBackendMode = Literal[
    "GEMINI_OMNI_INTERACTIONS",
    "VERTEX_VEO_ENTERPRISE",
    "HUMAN_BATCH_DESK",
]

GEMINI_OMNI_INTERACTIONS: FlowBackendMode = "GEMINI_OMNI_INTERACTIONS"
VERTEX_VEO_ENTERPRISE: FlowBackendMode = "VERTEX_VEO_ENTERPRISE"
HUMAN_BATCH_DESK: FlowBackendMode = "HUMAN_BATCH_DESK"

AWAITING_FLOW_BATCH = "AWAITING_FLOW_BATCH"
FLOW_BATCH_SLOT_CAP = 3
ADVANCED = "ADVANCED"
BACKPRESSURE_QUEUE_FULL = "BACKPRESSURE_QUEUE_FULL"

HEADLESS_CHECKPOINTS = (
    "SCENE_PLAN_APPROVED",
    "VOICE_READY",
    "ANIMATIC_APPROVED",
)

LEGAL_FORWARD_PATH = (
    "QUEUED",
    "SCOUTED",
    "EVIDENCE_AND_2K_LOCKED",
    "COMPLIANCE_PASSED",
    "SCENE_PLAN_APPROVED",
    "VOICE_READY",
    "MANIFEST_LINTED",
    "ANIMATIC_APPROVED",
    "CODE_RENDERED",
    AWAITING_FLOW_BATCH,
    "POST_FLOW_PROCESSING",
    "MASTERED",
    "PENDING_HUMAN_SIGNOFF",
    "READY_TO_UPLOAD",
    "PUBLISHED",
)

HEADLESS_FORWARD_PATH = tuple(
    state for state in LEGAL_FORWARD_PATH if state != AWAITING_FLOW_BATCH
)

DEFAULT_FLOW_MODE: FlowBackendMode = GEMINI_OMNI_INTERACTIONS
MS_PER_DAY = 86_400_000


class EpisodeNotFound(Exception):
    """Raised when ``episode_id`` is unknown to the scheduler store."""

    def __init__(self, episode_id: str) -> None:
        self.episode_id = episode_id
        super().__init__(f"episode not found: {episode_id}")


class IllegalTransition(Exception):
    """Raised when a requested move is not the next legal step for the mode."""

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
    episode_id: str
    from_state: str
    requested_state: str
    state: str
    status: str
    updated_at: int | None


@dataclass(frozen=True)
class ParkedEpisode:
    episode_id: str
    created_at: int
    parked_at: int | None


@dataclass
class EpisodeRecord:
    episode_id: str
    created_at: int
    flow_backend_mode: FlowBackendMode = DEFAULT_FLOW_MODE
    state: str = "QUEUED"
    updated_at: int | None = None
    parked_at: int | None = None


def legal_path_for(mode: FlowBackendMode) -> tuple[str, ...]:
    if mode == HUMAN_BATCH_DESK:
        return LEGAL_FORWARD_PATH
    return HEADLESS_FORWARD_PATH


def next_forward_state(current: str, mode: FlowBackendMode) -> str | None:
    path = legal_path_for(mode)
    try:
        index = path.index(current)
    except ValueError:
        return None
    if index + 1 >= len(path):
        return None
    return path[index + 1]


class ConveyorStore(Protocol):
    """Minimal persistence port consumed by ``ConveyorScheduler``."""

    def get_state(self, episode_id: str) -> str: ...

    def get_flow_backend_mode(self, episode_id: str) -> FlowBackendMode: ...

    def transition(self, episode_id: str, to_state: str) -> TransitionResult: ...

    def list_parked_batch_desk(self) -> tuple[ParkedEpisode, ...]: ...


@dataclass
class InMemoryConveyorStore:
    """Deterministic in-memory store for offline scheduler simulations."""

    episodes: dict[str, EpisodeRecord] = field(default_factory=dict)
    now: Callable[[], int] = field(default=lambda: 0)

    def register(
        self,
        episode_id: str,
        *,
        created_at: int,
        flow_backend_mode: FlowBackendMode = DEFAULT_FLOW_MODE,
        state: str = "QUEUED",
    ) -> None:
        self.episodes[episode_id] = EpisodeRecord(
            episode_id=episode_id,
            created_at=created_at,
            flow_backend_mode=flow_backend_mode,
            state=state,
            updated_at=created_at if state != "QUEUED" else None,
        )

    def get_state(self, episode_id: str) -> str:
        record = self._require(episode_id)
        return record.state

    def get_flow_backend_mode(self, episode_id: str) -> FlowBackendMode:
        return self._require(episode_id).flow_backend_mode

    def list_parked_batch_desk(self) -> tuple[ParkedEpisode, ...]:
        parked = [
            ParkedEpisode(
                episode_id=record.episode_id,
                created_at=record.created_at,
                parked_at=record.parked_at,
            )
            for record in self.episodes.values()
            if record.flow_backend_mode == HUMAN_BATCH_DESK
            and record.state == AWAITING_FLOW_BATCH
        ]
        parked.sort(key=lambda item: (item.created_at, item.episode_id))
        return tuple(parked)

    def transition(self, episode_id: str, to_state: str) -> TransitionResult:
        record = self._require(episode_id)
        current = record.state
        mode = record.flow_backend_mode
        path = legal_path_for(mode)
        self._require_adjacent(episode_id, current, to_state, path)

        if (
            to_state == AWAITING_FLOW_BATCH
            and mode == HUMAN_BATCH_DESK
            and len(self.list_parked_batch_desk()) >= FLOW_BATCH_SLOT_CAP
        ):
            return TransitionResult(
                episode_id=episode_id,
                from_state=current,
                requested_state=to_state,
                state=current,
                status=BACKPRESSURE_QUEUE_FULL,
                updated_at=None,
            )

        stamp = self._timestamp()
        record.state = to_state
        record.updated_at = stamp
        if to_state == AWAITING_FLOW_BATCH:
            record.parked_at = stamp
        elif current == AWAITING_FLOW_BATCH:
            record.parked_at = None

        return TransitionResult(
            episode_id=episode_id,
            from_state=current,
            requested_state=to_state,
            state=to_state,
            status=ADVANCED,
            updated_at=stamp,
        )

    def _require(self, episode_id: str) -> EpisodeRecord:
        record = self.episodes.get(episode_id)
        if record is None:
            raise EpisodeNotFound(episode_id)
        return record

    def _timestamp(self) -> int:
        value = self.now()
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError("now() must return an int epoch-millisecond timestamp")
        return value

    @staticmethod
    def _require_adjacent(
        episode_id: str,
        current: str,
        to_state: str,
        path: tuple[str, ...],
    ) -> None:
        index = {state: position for position, state in enumerate(path)}
        current_index = index.get(current)
        if current_index is None:
            raise IllegalTransition(
                episode_id, current, to_state, "off the legal forward path"
            )
        if current_index + 1 >= len(path):
            raise IllegalTransition(episode_id, current, to_state, "terminal state")
        expected = path[current_index + 1]
        if to_state == expected:
            return
        target_index = index.get(to_state)
        if target_index is None:
            reason = "not a legal conveyor state"
        elif target_index < current_index:
            reason = "backward move"
        elif target_index == current_index:
            reason = "same state is not a forward move"
        else:
            reason = "skip"
        raise IllegalTransition(episode_id, current, to_state, reason)


@dataclass(frozen=True)
class AdvanceResult:
    """One scheduler step outcome."""

    transition: TransitionResult | None
    blocked: bool = False
    reason: str | None = None


class ConveyorScheduler:
    """Mode-aware multi-episode conveyor coordinator.

    ``now`` is injected and runs only when a transition commits.
    The scheduler never sleeps and never opens a network connection.
    """

    def __init__(self, store: ConveyorStore, *, now: Callable[[], int]) -> None:
        if not callable(now):
            raise TypeError("now must be a callable returning integer epoch milliseconds")
        self._store = store
        self._now = now

    def scout(self, episode_id: str) -> TransitionResult:
        """Advance ``QUEUED`` -> ``SCOUTED`` regardless of batch-desk parking."""
        state = self._store.get_state(episode_id)
        if state != "QUEUED":
            raise IllegalTransition(
                episode_id,
                state,
                "SCOUTED",
                "scouting only applies from QUEUED",
            )
        return self._store.transition(episode_id, "SCOUTED")

    def advance_step(self, episode_id: str) -> AdvanceResult:
        """Advance one autonomous step for the episode's backend mode."""
        mode = self._store.get_flow_backend_mode(episode_id)
        current = self._store.get_state(episode_id)
        target = next_forward_state(current, mode)
        if target is None:
            return AdvanceResult(transition=None, blocked=True, reason="terminal state")
        result = self._store.transition(episode_id, target)
        if result.status == BACKPRESSURE_QUEUE_FULL:
            return AdvanceResult(
                transition=result,
                blocked=True,
                reason=BACKPRESSURE_QUEUE_FULL,
            )
        return AdvanceResult(transition=result)

    def advance_headless_to_mastered(self, episode_id: str) -> list[TransitionResult]:
        """Walk a headless episode through plan/voice/animatic gates to ``MASTERED``."""
        mode = self._store.get_flow_backend_mode(episode_id)
        if mode == HUMAN_BATCH_DESK:
            raise ValueError("advance_headless_to_mastered requires a headless backend mode")
        moves: list[TransitionResult] = []
        while self._store.get_state(episode_id) != "MASTERED":
            step = self.advance_step(episode_id)
            if step.transition is None or step.blocked:
                raise RuntimeError(
                    f"headless stall for {episode_id} at {self._store.get_state(episode_id)}"
                )
            moves.append(step.transition)
        return moves

    def park_for_batch_desk(self, episode_id: str) -> TransitionResult:
        """Park a Batch Desk episode at ``CODE_RENDERED`` into the flow batch queue."""
        mode = self._store.get_flow_backend_mode(episode_id)
        if mode != HUMAN_BATCH_DESK:
            raise ValueError("park_for_batch_desk requires HUMAN_BATCH_DESK mode")
        state = self._store.get_state(episode_id)
        if state != "CODE_RENDERED":
            raise IllegalTransition(
                episode_id,
                state,
                AWAITING_FLOW_BATCH,
                "batch parking only applies from CODE_RENDERED",
            )
        return self._store.transition(episode_id, AWAITING_FLOW_BATCH)

    def drain_oldest_parked(self) -> TransitionResult | None:
        """Move the oldest parked Batch Desk episode to ``POST_FLOW_PROCESSING``."""
        parked = self._store.list_parked_batch_desk()
        if not parked:
            return None
        oldest = parked[0].episode_id
        if self._store.get_state(oldest) != AWAITING_FLOW_BATCH:
            return None
        return self._store.transition(oldest, "POST_FLOW_PROCESSING")

    def parked_batch_count(self) -> int:
        return len(self._store.list_parked_batch_desk())

    def list_parked_batch_desk(self) -> tuple[ParkedEpisode, ...]:
        return self._store.list_parked_batch_desk()