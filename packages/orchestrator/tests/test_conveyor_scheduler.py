"""Conveyor scheduler simulations. No network and no sleep."""

from __future__ import annotations

import pytest

from orchestrator.conveyor_scheduler import (
    ADVANCED,
    AWAITING_FLOW_BATCH,
    BACKPRESSURE_QUEUE_FULL,
    FLOW_BATCH_SLOT_CAP,
    GEMINI_OMNI_INTERACTIONS,
    HEADLESS_CHECKPOINTS,
    HUMAN_BATCH_DESK,
    MS_PER_DAY,
    ConveyorScheduler,
    IllegalTransition,
    InMemoryConveyorStore,
)


class Clock:
    """Injected millisecond clock. Each call advances by one millisecond."""

    def __init__(self, start: int = 1_000) -> None:
        self.now_ms = start

    def __call__(self) -> int:
        self.now_ms += 1
        return self.now_ms


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(clock: Clock) -> InMemoryConveyorStore:
    return InMemoryConveyorStore(now=clock)


@pytest.fixture
def scheduler(store: InMemoryConveyorStore, clock: Clock) -> ConveyorScheduler:
    return ConveyorScheduler(store, now=clock)


def test_headless_walks_queued_to_mastered_without_human_wait(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
) -> None:
    store.register("ep-headless", created_at=10, flow_backend_mode=GEMINI_OMNI_INTERACTIONS)
    moves = scheduler.advance_headless_to_mastered("ep-headless")
    assert moves
    assert all(move.status == ADVANCED for move in moves)
    assert scheduler._store.get_state("ep-headless") == "MASTERED"
    assert scheduler.parked_batch_count() == 0


def test_headless_hits_plan_voice_animatic_checkpoints_in_order(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
) -> None:
    store.register("ep-gates", created_at=20, flow_backend_mode=GEMINI_OMNI_INTERACTIONS)
    seen: list[str] = []
    while scheduler._store.get_state("ep-gates") != "MASTERED":
        step = scheduler.advance_step("ep-gates")
        assert step.transition is not None
        assert step.transition.status == ADVANCED
        state = step.transition.state
        if state in HEADLESS_CHECKPOINTS:
            seen.append(state)
    assert seen == list(HEADLESS_CHECKPOINTS)


def test_headless_never_parks_in_flow_batch_queue(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
) -> None:
    store.register("ep-skip", created_at=30, flow_backend_mode=GEMINI_OMNI_INTERACTIONS)
    scheduler.advance_headless_to_mastered("ep-skip")
    assert AWAITING_FLOW_BATCH not in {
        scheduler._store.get_state(episode.episode_id)
        for episode in store.episodes.values()
    }


def test_batch_desk_three_slots_fifo_oldest_first(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
) -> None:
    for episode_id, created_at in (("ep-c", 300), ("ep-a", 100), ("ep-b", 200)):
        store.register(
            episode_id,
            created_at=created_at,
            flow_backend_mode=HUMAN_BATCH_DESK,
            state="CODE_RENDERED",
        )
        result = scheduler.park_for_batch_desk(episode_id)
        assert result.status == ADVANCED
    parked = scheduler.list_parked_batch_desk()
    assert [item.episode_id for item in parked] == ["ep-a", "ep-b", "ep-c"]
    assert FLOW_BATCH_SLOT_CAP == 3


def test_fourth_batch_desk_episode_gets_backpressure_and_stays(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
    clock: Clock,
) -> None:
    for index, episode_id in enumerate(("ep-a", "ep-b", "ep-c")):
        store.register(
            episode_id,
            created_at=100 + index,
            flow_backend_mode=HUMAN_BATCH_DESK,
            state="CODE_RENDERED",
        )
        scheduler.park_for_batch_desk(episode_id)
    store.register("ep-d", created_at=50, flow_backend_mode=HUMAN_BATCH_DESK, state="CODE_RENDERED")
    seen = clock.now_ms
    held = scheduler.park_for_batch_desk("ep-d")
    assert held.status == BACKPRESSURE_QUEUE_FULL
    assert held.state == "CODE_RENDERED"
    assert held.updated_at is None
    assert scheduler._store.get_state("ep-d") == "CODE_RENDERED"
    assert clock.now_ms == seen


def test_three_day_parked_episode_does_not_block_later_scouting(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
    clock: Clock,
) -> None:
    long_park = 3 * MS_PER_DAY
    for index, episode_id in enumerate(("ep-a", "ep-b", "ep-c")):
        store.register(
            episode_id,
            created_at=100 + index,
            flow_backend_mode=HUMAN_BATCH_DESK,
            state="CODE_RENDERED",
        )
        scheduler.park_for_batch_desk(episode_id)
    clock.now_ms = long_park + 5000
    store.register("ep-n-plus-2", created_at=long_park + 6000, flow_backend_mode=HUMAN_BATCH_DESK)
    scouted = scheduler.scout("ep-n-plus-2")
    assert scouted.status == ADVANCED
    assert scouted.state == "SCOUTED"
    assert scheduler.parked_batch_count() == 3


def test_draining_oldest_frees_slot_and_preserves_fifo(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
) -> None:
    for episode_id, created_at in (("ep-c", 300), ("ep-a", 100), ("ep-b", 200)):
        store.register(
            episode_id,
            created_at=created_at,
            flow_backend_mode=HUMAN_BATCH_DESK,
            state="CODE_RENDERED",
        )
        scheduler.park_for_batch_desk(episode_id)
    drained = scheduler.drain_oldest_parked()
    assert drained is not None
    assert drained.episode_id == "ep-a"
    assert drained.state == "POST_FLOW_PROCESSING"

    store.register("ep-d", created_at=50, flow_backend_mode=HUMAN_BATCH_DESK, state="CODE_RENDERED")
    admitted = scheduler.park_for_batch_desk("ep-d")
    assert admitted.status == ADVANCED
    assert [item.episode_id for item in scheduler.list_parked_batch_desk()] == [
        "ep-d",
        "ep-b",
        "ep-c",
    ]


def test_scout_rejects_non_queued_episode(scheduler: ConveyorScheduler, store: InMemoryConveyorStore) -> None:
    store.register("ep-busy", created_at=1, flow_backend_mode=HUMAN_BATCH_DESK, state="SCOUTED")
    with pytest.raises(IllegalTransition, match="scouting only applies from QUEUED"):
        scheduler.scout("ep-busy")


def test_batch_desk_path_requires_park_before_post_flow(
    scheduler: ConveyorScheduler,
    store: InMemoryConveyorStore,
) -> None:
    store.register("ep-batch", created_at=5, flow_backend_mode=HUMAN_BATCH_DESK, state="CODE_RENDERED")
    with pytest.raises(IllegalTransition, match="skip"):
        scheduler._store.transition("ep-batch", "POST_FLOW_PROCESSING")
    parked = scheduler.park_for_batch_desk("ep-batch")
    assert parked.state == AWAITING_FLOW_BATCH
    advanced = scheduler.drain_oldest_parked()
    assert advanced is not None
    assert advanced.state == "POST_FLOW_PROCESSING"