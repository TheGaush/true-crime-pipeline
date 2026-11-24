"""Flow dispatch and optional AWAITING_FLOW_BATCH parking (Task 095)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from orchestrator.flow_batch_parker import (
    AWAITING_FLOW_BATCH,
    AccountDailyLedger,
    DailyResetLockError,
    FlowBatchParker,
    FlowDispatchReceipt,
    FlowJobDispatch,
    NeighborFallbackError,
    build_neighbor_safe_fallback,
    compute_idempotency_key,
    is_daily_reset_locked,
    next_reset_from_first_spend,
    select_non_neighbor_fallback_engine,
)


@dataclass
class _RecordingPort:
    calls: list[tuple[FlowJobDispatch, ...]] = field(default_factory=list)

    def dispatch_flow_jobs(self, jobs: tuple[FlowJobDispatch, ...] | list[FlowJobDispatch]):
        batch = tuple(jobs)
        self.calls.append(batch)
        return tuple(
            FlowDispatchReceipt(
                flow_job_id=job.flow_job_id,
                provider_route=job.provider_route,
                state="SUBMITTING",
            )
            for job in batch
        )


def test_idempotency_key_is_stable_and_unique_per_scene() -> None:
    key_a = compute_idempotency_key("ep_1", "scene_a", "prompt alpha")
    key_b = compute_idempotency_key("ep_1", "scene_b", "prompt alpha")
    key_a_retry = compute_idempotency_key("ep_1", "scene_a", "prompt alpha", attempt=2)
    assert key_a != key_b
    assert key_a != key_a_retry
    assert len(key_a) == 64


def test_non_neighbor_fallback_between_stickman_neighbors() -> None:
    engine = select_non_neighbor_fallback_engine("CODE_STICKMAN", "CODE_STICKMAN")
    assert engine == "STILL_2K_PANZOOM"
    spec = build_neighbor_safe_fallback(
        prev_engine="CODE_STICKMAN",
        next_engine="CODE_STICKMAN",
    )
    assert spec.visual_engine == "STILL_2K_PANZOOM"
    assert spec.motif_component == "Illustrative2KPanZoom"


def test_create_flow_job_rejects_neighbor_fallback_collision() -> None:
    port = _RecordingPort()
    parker = FlowBatchParker(port, now_ms=1_700_000_000_000, headless=True)
    bad = build_neighbor_safe_fallback(
        prev_engine="STILL_2K_PANZOOM",
        next_engine="AUDIO_EVIDENCE_CARD",
    )
    bad = type(bad)(
        visual_engine="STILL_2K_PANZOOM",
        motif_component="Illustrative2KPanZoom",
        reason="bad",
    )
    with pytest.raises(NeighborFallbackError):
        parker.create_flow_job(
            flow_job_id="job_1",
            episode_id="ep_1",
            scene_id="scene_1",
            prompt_mode="TEXT_TO_VIDEO",
            prompt_v1="Monochrome tracking shot",
            prompt_v2_safe="Monochrome camera move across an empty room",
            provider_route="GEMINI_OMNI_INTERACTIONS",
            prev_neighbor_engine="STILL_2K_PANZOOM",
            next_neighbor_engine="CODE_STICKMAN",
            fallback=bad,
        )


def test_gemini_headless_dispatches_immediately_without_parking() -> None:
    port = _RecordingPort()
    parker = FlowBatchParker(port, now_ms=1000, headless=True)
    job = parker.create_flow_job(
        flow_job_id="job_gemini",
        episode_id="ep_gemini",
        scene_id="scene_hero",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1="Monochrome tracking shot",
        prompt_v2_safe="Monochrome camera move across an empty room",
        provider_route="GEMINI_OMNI_INTERACTIONS",
        prev_neighbor_engine="CODE_STICKMAN",
        next_neighbor_engine="CODE_STICKMAN",
    )
    outcome = parker.dispatch_or_park(
        episode_id="ep_gemini",
        provider_route="GEMINI_OMNI_INTERACTIONS",
        jobs=[job],
    )
    assert outcome.dispatched is True
    assert outcome.parked is False
    assert outcome.episode_state != AWAITING_FLOW_BATCH
    assert outcome.flow_jobs[0].state == "SUBMITTING"
    assert len(port.calls) == 1
    assert port.calls[0][0].provider_route == "GEMINI_OMNI_INTERACTIONS"


def test_vertex_dispatches_immediately_via_injected_port() -> None:
    port = _RecordingPort()
    parker = FlowBatchParker(port, now_ms=2000, headless=True)
    job = parker.create_flow_job(
        flow_job_id="job_vertex",
        episode_id="ep_vertex",
        scene_id="scene_vertex",
        prompt_mode="FIRST_FRAME",
        prompt_v1="Slow push-in on evidence table",
        prompt_v2_safe="Static wide shot of empty table",
        provider_route="VERTEX_VEO_ENTERPRISE",
    )
    outcome = parker.dispatch_or_park(
        episode_id="ep_vertex",
        provider_route="VERTEX_VEO_ENTERPRISE",
        jobs=[job],
    )
    assert outcome.dispatched
    assert not outcome.parked
    assert port.calls[0][0].provider_route == "VERTEX_VEO_ENTERPRISE"


def test_human_batch_desk_parks_in_awaiting_flow_batch_when_unlocked() -> None:
    port = _RecordingPort()
    first_spend = 1_000_000
    reset_at = next_reset_from_first_spend(first_spend)
    account = AccountDailyLedger(
        account_id="acct_1",
        daily_credits_left=50,
        first_daily_spend_utc_ms=first_spend,
        next_daily_reset_utc_ms=reset_at,
    )
    parker = FlowBatchParker(port, now_ms=reset_at, headless=False)
    job = parker.create_flow_job(
        flow_job_id="job_desk",
        episode_id="ep_desk",
        scene_id="scene_desk",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1="Desk prompt",
        prompt_v2_safe="Desk safe prompt",
        provider_route="HUMAN_BATCH_DESK",
        assigned_account_id="acct_1",
    )
    outcome = parker.dispatch_or_park(
        episode_id="ep_desk",
        provider_route="HUMAN_BATCH_DESK",
        jobs=[job],
        account=account,
    )
    assert outcome.parked is True
    assert outcome.episode_state == AWAITING_FLOW_BATCH
    assert outcome.dispatched is True
    assert len(port.calls) == 1


def test_human_batch_desk_refuses_dispatch_before_daily_reset() -> None:
    port = _RecordingPort()
    first_spend = 5_000_000
    reset_at = next_reset_from_first_spend(first_spend)
    account = AccountDailyLedger(
        account_id="acct_lock",
        daily_credits_left=0,
        first_daily_spend_utc_ms=first_spend,
        next_daily_reset_utc_ms=reset_at,
    )
    assert is_daily_reset_locked(now_ms=reset_at - 1, next_daily_reset_utc_ms=reset_at)
    parker = FlowBatchParker(port, now_ms=reset_at - 1, headless=False)
    job = parker.create_flow_job(
        flow_job_id="job_lock",
        episode_id="ep_lock",
        scene_id="scene_lock",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1="Locked prompt",
        prompt_v2_safe="Locked safe",
        provider_route="HUMAN_BATCH_DESK",
        assigned_account_id="acct_lock",
    )
    with pytest.raises(DailyResetLockError) as exc:
        parker.dispatch_or_park(
            episode_id="ep_lock",
            provider_route="HUMAN_BATCH_DESK",
            jobs=[job],
            account=account,
        )
    assert exc.value.next_daily_reset_utc_ms == reset_at
    assert port.calls == []


def test_headless_mode_never_waits_for_human_shift() -> None:
    """GEMINI_OMNI must dispatch even when a Batch Desk account is locked."""

    port = _RecordingPort()
    locked_account = AccountDailyLedger(
        account_id="acct_locked",
        daily_credits_left=0,
        first_daily_spend_utc_ms=1_000,
        next_daily_reset_utc_ms=next_reset_from_first_spend(1_000),
    )
    parker = FlowBatchParker(port, now_ms=500, headless=True)
    job = parker.create_flow_job(
        flow_job_id="job_headless",
        episode_id="ep_headless",
        scene_id="scene_h",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1="Autonomous prompt",
        prompt_v2_safe="Autonomous safe",
        provider_route="GEMINI_OMNI_INTERACTIONS",
    )
    outcome = parker.dispatch_or_park(
        episode_id="ep_headless",
        provider_route="GEMINI_OMNI_INTERACTIONS",
        jobs=[job],
        account=locked_account,
    )
    assert outcome.dispatched
    assert not outcome.parked
    assert len(port.calls) == 1


def test_batch_desk_retry_after_reset_unlocks() -> None:
    port = _RecordingPort()
    first_spend = 9_000_000
    reset_at = next_reset_from_first_spend(first_spend)
    account = AccountDailyLedger(
        account_id="acct_retry",
        daily_credits_left=50,
        first_daily_spend_utc_ms=first_spend,
        next_daily_reset_utc_ms=reset_at,
    )
    job = FlowBatchParker(_RecordingPort(), now_ms=reset_at - 1, headless=False).create_flow_job(
        flow_job_id="job_retry",
        episode_id="ep_retry",
        scene_id="scene_retry",
        prompt_mode="TEXT_TO_VIDEO",
        prompt_v1="Retry prompt",
        prompt_v2_safe="Retry safe",
        provider_route="HUMAN_BATCH_DESK",
    )
    parker = FlowBatchParker(port, now_ms=reset_at, headless=False)
    outcome = parker.try_batch_desk_dispatch(
        episode_id="ep_retry",
        jobs=[job],
        account=account,
    )
    assert outcome.dispatched
    assert outcome.daily_reset_locked is False
    assert len(port.calls) == 1