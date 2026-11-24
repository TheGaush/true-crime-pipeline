"""Per-shift saturation re-check and single-fire post-Flow wakeup.

Before each day's Flow spend the watcher consults ``PreRenderSaturationGate``
(when injected) or raw saturation metrics. Abort ``ABORTED_COPYCAT_WAVE`` when
``N_14d_wave > 3`` or ``has_90d_200k_kill == 1``, unless the sunk-cost guard
finishes the episode instead.

When every ``flow_jobs`` row is terminal (``ACCEPTED`` or ``SWITCHED_TO_FALLBACK``),
transition the episode to ``POST_FLOW_PROCESSING`` exactly once.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

WAVE_ABORT_ABOVE = 3
SUNK_COST_SPENT_ABOVE = 0.50
SUNK_COST_WAVE_AT_MOST = 5

ABORTED_COPYCAT_WAVE = "ABORTED_COPYCAT_WAVE"
DECISION_FINISH = "FINISH"
AWAITING_FLOW_BATCH = "AWAITING_FLOW_BATCH"
POST_FLOW_PROCESSING = "POST_FLOW_PROCESSING"

PHASE_PER_SHIFT_SATURATION_RECHECK = "PER_SHIFT_SATURATION_RECHECK"

TERMINAL_FLOW_JOB_STATES = frozenset({"ACCEPTED", "SWITCHED_TO_FALLBACK"})


class SaturationGatePort(Protocol):
    """Task 031 ``PreRenderSaturationGate`` surface consumed by the watcher."""

    def before_flow_spend(
        self,
        *,
        queries: Sequence[str],
        now_ms: int,
        spent_credits_pct: float = 0.0,
    ) -> object:
        """Day 1 re-check before any Flow credit is spent."""

    def before_batch_desk_day(
        self,
        batch_day: int,
        *,
        queries: Sequence[str],
        spent_credits_pct: float,
        now_ms: int,
    ) -> object:
        """Later Batch Desk day re-check."""


@dataclass(frozen=True, slots=True)
class ShiftRecheckOutcome:
    """Result of one per-shift saturation decision for an episode."""

    episode_id: str
    batch_day: int
    phase: str
    decision: str
    episode_state: str
    aborted: int
    sunk_cost_override: int
    n_14d_wave: int
    has_90d_200k_kill: int
    tier1_giant_hit: int
    spent_credits_pct: float


@dataclass(frozen=True, slots=True)
class PostFlowWakeupResult:
    """Single-fire transition into overnight post-Flow processing."""

    episode_id: str
    from_state: str
    to_state: str
    fired: bool
    wakeup_count: int


@dataclass
class PostFlowWatcher:
    """Per-episode saturation watcher and post-Flow state driver.

    ``post_flow_wakeup_count`` tracks how many times
    ``POST_FLOW_PROCESSING`` was committed (must stay at most 1).
    """

    episode_id: str
    episode_state: str = AWAITING_FLOW_BATCH
    post_flow_wakeup_count: int = 0

    def before_shift_flow_spend(
        self,
        *,
        gate: SaturationGatePort,
        batch_day: int,
        queries: Sequence[str],
        spent_credits_pct: float,
        now_ms: int,
    ) -> ShiftRecheckOutcome:
        """Run Task 031 gate hooks, then apply the episode-level decision."""

        if batch_day == 1:
            raw = gate.before_flow_spend(
                queries=queries,
                now_ms=now_ms,
                spent_credits_pct=spent_credits_pct,
            )
        else:
            raw = gate.before_batch_desk_day(
                batch_day,
                queries=queries,
                spent_credits_pct=spent_credits_pct,
                now_ms=now_ms,
            )
        return self._apply_gate_result(batch_day, raw)

    def evaluate_shift_metrics(
        self,
        *,
        batch_day: int,
        n_14d_wave: int,
        has_90d_200k_kill: int,
        tier1_giant_hit: int,
        spent_credits_pct: float,
    ) -> ShiftRecheckOutcome:
        """Apply saturation rules from pre-computed metrics (no ``search.list``)."""

        decision, sunk_cost_override, aborted = decide_pre_shift(
            n_14d_wave=n_14d_wave,
            has_90d_200k_kill=has_90d_200k_kill,
            tier1_giant_hit=tier1_giant_hit,
            spent_credits_pct=spent_credits_pct,
        )
        return self._commit_shift_outcome(
            batch_day=batch_day,
            decision=decision,
            aborted=aborted,
            sunk_cost_override=sunk_cost_override,
            n_14d_wave=n_14d_wave,
            has_90d_200k_kill=has_90d_200k_kill,
            tier1_giant_hit=tier1_giant_hit,
            spent_credits_pct=spent_credits_pct,
        )

    def maybe_wakeup_post_flow(
        self,
        flow_jobs: Sequence[Mapping[str, object]] | Sequence[str],
    ) -> PostFlowWakeupResult | None:
        """Move to ``POST_FLOW_PROCESSING`` when all jobs are terminal.

        Returns ``None`` when jobs are not all terminal. When already in
        ``POST_FLOW_PROCESSING``, returns a result with ``fired=False`` and
        does not increment ``post_flow_wakeup_count``.
        """

        if not _all_flow_jobs_terminal(flow_jobs):
            return None
        if self.episode_state == POST_FLOW_PROCESSING:
            return PostFlowWakeupResult(
                episode_id=self.episode_id,
                from_state=POST_FLOW_PROCESSING,
                to_state=POST_FLOW_PROCESSING,
                fired=False,
                wakeup_count=self.post_flow_wakeup_count,
            )
        if self.post_flow_wakeup_count >= 1:
            return PostFlowWakeupResult(
                episode_id=self.episode_id,
                from_state=self.episode_state,
                to_state=self.episode_state,
                fired=False,
                wakeup_count=self.post_flow_wakeup_count,
            )
        prior = self.episode_state
        self.episode_state = POST_FLOW_PROCESSING
        self.post_flow_wakeup_count = 1
        return PostFlowWakeupResult(
            episode_id=self.episode_id,
            from_state=prior,
            to_state=POST_FLOW_PROCESSING,
            fired=True,
            wakeup_count=1,
        )

    def _apply_gate_result(self, batch_day: int, raw: object) -> ShiftRecheckOutcome:
        decision = str(_field(raw, "decision"))
        aborted = int(_field(raw, "aborted"))
        sunk_cost_override = int(_field(raw, "sunk_cost_override"))
        return self._commit_shift_outcome(
            batch_day=batch_day,
            decision=decision,
            aborted=aborted,
            sunk_cost_override=sunk_cost_override,
            n_14d_wave=int(_field(raw, "n_14d_wave")),
            has_90d_200k_kill=int(_field(raw, "has_90d_200k_kill")),
            tier1_giant_hit=int(_field(raw, "tier1_giant_hit")),
            spent_credits_pct=float(_field(raw, "spent_credits_pct")),
        )

    def _commit_shift_outcome(
        self,
        *,
        batch_day: int,
        decision: str,
        aborted: int,
        sunk_cost_override: int,
        n_14d_wave: int,
        has_90d_200k_kill: int,
        tier1_giant_hit: int,
        spent_credits_pct: float,
    ) -> ShiftRecheckOutcome:
        if aborted:
            self.episode_state = ABORTED_COPYCAT_WAVE
        return ShiftRecheckOutcome(
            episode_id=self.episode_id,
            batch_day=batch_day,
            phase=PHASE_PER_SHIFT_SATURATION_RECHECK,
            decision=decision,
            episode_state=self.episode_state,
            aborted=aborted,
            sunk_cost_override=sunk_cost_override,
            n_14d_wave=n_14d_wave,
            has_90d_200k_kill=has_90d_200k_kill,
            tier1_giant_hit=tier1_giant_hit,
            spent_credits_pct=spent_credits_pct,
        )


def decide_pre_shift(
    *,
    n_14d_wave: int,
    has_90d_200k_kill: int,
    tier1_giant_hit: int,
    spent_credits_pct: float,
) -> tuple[str, int, int]:
    """Return ``(decision, sunk_cost_override, aborted)``.

    Mirrors Task 031 ``decide_pre_render`` so the orchestrator can run offline
    tests without importing ``agent1_scout``.
    """

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


def _all_flow_jobs_terminal(
    flow_jobs: Sequence[Mapping[str, object]] | Sequence[str],
) -> bool:
    if not flow_jobs:
        return False
    for job in flow_jobs:
        if isinstance(job, str):
            state = job
        elif isinstance(job, Mapping):
            state = str(job.get("state", ""))
        else:
            raise TypeError("flow_jobs entries must be mappings or state strings")
        if state not in TERMINAL_FLOW_JOB_STATES:
            return False
    return True


def _field(raw: object, name: str) -> object:
    if isinstance(raw, Mapping):
        return raw[name]
    return getattr(raw, name)