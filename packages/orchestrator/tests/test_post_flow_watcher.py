"""Per-shift saturation watcher and post-Flow wakeup (Task 096)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from orchestrator.post_flow_watcher import (
    ABORTED_COPYCAT_WAVE,
    AWAITING_FLOW_BATCH,
    DECISION_FINISH,
    POST_FLOW_PROCESSING,
    PostFlowWatcher,
    decide_pre_shift,
)


def test_day2_aborts_large_wave_at_twenty_percent_spent() -> None:
    watcher = PostFlowWatcher("ep-b", episode_state=AWAITING_FLOW_BATCH)
    outcome = watcher.evaluate_shift_metrics(
        batch_day=2,
        n_14d_wave=6,
        has_90d_200k_kill=0,
        tier1_giant_hit=0,
        spent_credits_pct=0.20,
    )
    assert outcome.decision == ABORTED_COPYCAT_WAVE
    assert outcome.aborted == 1
    assert outcome.sunk_cost_override == 0
    assert outcome.episode_state == ABORTED_COPYCAT_WAVE
    assert watcher.episode_state == ABORTED_COPYCAT_WAVE
    assert outcome.spent_credits_pct == 0.20
    assert outcome.n_14d_wave > 5


def test_sunk_cost_override_finishes_at_seventy_five_percent() -> None:
    watcher = PostFlowWatcher("ep-c", episode_state=AWAITING_FLOW_BATCH)
    outcome = watcher.evaluate_shift_metrics(
        batch_day=3,
        n_14d_wave=4,
        has_90d_200k_kill=0,
        tier1_giant_hit=0,
        spent_credits_pct=0.75,
    )
    assert outcome.decision == DECISION_FINISH
    assert outcome.aborted == 0
    assert outcome.sunk_cost_override == 1
    assert watcher.episode_state == AWAITING_FLOW_BATCH


def test_tier1_giant_blocks_sunk_cost_override() -> None:
    watcher = PostFlowWatcher("ep-d", episode_state=AWAITING_FLOW_BATCH)
    outcome = watcher.evaluate_shift_metrics(
        batch_day=2,
        n_14d_wave=4,
        has_90d_200k_kill=0,
        tier1_giant_hit=1,
        spent_credits_pct=0.75,
    )
    assert outcome.decision == ABORTED_COPYCAT_WAVE
    assert outcome.sunk_cost_override == 0
    assert outcome.aborted == 1
    assert watcher.episode_state == ABORTED_COPYCAT_WAVE


def test_90d_kill_aborts_at_low_spend() -> None:
    decision, override, aborted = decide_pre_shift(
        n_14d_wave=2,
        has_90d_200k_kill=1,
        tier1_giant_hit=0,
        spent_credits_pct=0.20,
    )
    assert decision == ABORTED_COPYCAT_WAVE
    assert override == 0
    assert aborted == 1


def test_90d_kill_finishes_via_sunk_cost_when_past_half() -> None:
    decision, override, aborted = decide_pre_shift(
        n_14d_wave=2,
        has_90d_200k_kill=1,
        tier1_giant_hit=0,
        spent_credits_pct=0.80,
    )
    assert decision == DECISION_FINISH
    assert override == 1
    assert aborted == 0


@dataclass
class _FakeGateResult:
    decision: str
    aborted: int
    sunk_cost_override: int
    n_14d_wave: int
    has_90d_200k_kill: int
    tier1_giant_hit: int
    spent_credits_pct: float


class _StubGate:
    def __init__(self, result: _FakeGateResult) -> None:
        self.result = result
        self.calls: list[tuple[str, int]] = []

    def before_flow_spend(self, **kwargs: object) -> _FakeGateResult:
        self.calls.append(("before_flow_spend", 1))
        return self.result

    def before_batch_desk_day(
        self,
        batch_day: int,
        **kwargs: object,
    ) -> _FakeGateResult:
        self.calls.append(("before_batch_desk_day", batch_day))
        return self.result


def test_before_shift_flow_spend_delegates_to_gate_on_day2() -> None:
    result = _FakeGateResult(
        decision=ABORTED_COPYCAT_WAVE,
        aborted=1,
        sunk_cost_override=0,
        n_14d_wave=6,
        has_90d_200k_kill=0,
        tier1_giant_hit=0,
        spent_credits_pct=0.20,
    )
    gate = _StubGate(result)
    watcher = PostFlowWatcher("ep-gate", episode_state=AWAITING_FLOW_BATCH)
    outcome = watcher.before_shift_flow_spend(
        gate=gate,
        batch_day=2,
        queries=("a", "b", "c"),
        spent_credits_pct=0.20,
        now_ms=1_763_904_000_000,
    )
    assert gate.calls == [("before_batch_desk_day", 2)]
    assert outcome.decision == ABORTED_COPYCAT_WAVE
    assert watcher.episode_state == ABORTED_COPYCAT_WAVE


def test_post_flow_wakeup_fires_once_when_all_jobs_terminal() -> None:
    watcher = PostFlowWatcher("ep-wake", episode_state=AWAITING_FLOW_BATCH)
    jobs = [
        {"flow_job_id": "fj-1", "state": "ACCEPTED"},
        {"flow_job_id": "fj-2", "state": "SWITCHED_TO_FALLBACK"},
    ]
    first = watcher.maybe_wakeup_post_flow(jobs)
    assert first is not None
    assert first.fired is True
    assert first.from_state == AWAITING_FLOW_BATCH
    assert first.to_state == POST_FLOW_PROCESSING
    assert watcher.episode_state == POST_FLOW_PROCESSING
    assert watcher.post_flow_wakeup_count == 1

    second = watcher.maybe_wakeup_post_flow(jobs)
    assert second is not None
    assert second.fired is False
    assert watcher.post_flow_wakeup_count == 1
    assert watcher.episode_state == POST_FLOW_PROCESSING


def test_post_flow_wakeup_waits_on_non_terminal_jobs() -> None:
    watcher = PostFlowWatcher("ep-pend", episode_state=AWAITING_FLOW_BATCH)
    jobs = [
        {"state": "ACCEPTED"},
        {"state": "RUNNING"},
    ]
    assert watcher.maybe_wakeup_post_flow(jobs) is None
    assert watcher.episode_state == AWAITING_FLOW_BATCH
    assert watcher.post_flow_wakeup_count == 0


def test_post_flow_wakeup_requires_at_least_one_job() -> None:
    watcher = PostFlowWatcher("ep-empty", episode_state=AWAITING_FLOW_BATCH)
    assert watcher.maybe_wakeup_post_flow([]) is None


def test_post_flow_wakeup_accepts_state_strings() -> None:
    watcher = PostFlowWatcher("ep-str", episode_state=AWAITING_FLOW_BATCH)
    fired = watcher.maybe_wakeup_post_flow(["ACCEPTED", "SWITCHED_TO_FALLBACK"])
    assert fired is not None
    assert fired.fired is True


def test_flow_job_entry_type_guard() -> None:
    watcher = PostFlowWatcher("ep-bad", episode_state=AWAITING_FLOW_BATCH)
    with pytest.raises(TypeError):
        watcher.maybe_wakeup_post_flow([42])  # type: ignore[list-item]