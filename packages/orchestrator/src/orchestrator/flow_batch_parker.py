"""Flow job staging, headless dispatch, and optional Batch Desk parking (Task 095).

Creates durable ``flow_jobs`` payloads with neighbor-safe ``fallback_spec_json``,
dispatches ``GEMINI_OMNI_INTERACTIONS`` / ``VERTEX_VEO_ENTERPRISE`` immediately through
an injected port, and parks ``HUMAN_BATCH_DESK`` episodes in ``AWAITING_FLOW_BATCH``
while the per-account ``24h + 5m`` reset window is still locked.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

AWAITING_FLOW_BATCH = "AWAITING_FLOW_BATCH"
DAILY_RESET_WINDOW_MS = 86_400_000 + 300_000

FlowBackendMode = Literal[
    "GEMINI_OMNI_INTERACTIONS",
    "VERTEX_VEO_ENTERPRISE",
    "HUMAN_BATCH_DESK",
]
VideoPromptMode = Literal["TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]
FlowJobState = Literal[
    "PENDING",
    "SUBMITTING",
    "RUNNING",
    "UNKNOWN_RECONCILE",
    "PENDING_MANUAL_SPOT_CHECK",
    "STRIKE_1_RETRY_SAFE",
    "ACCEPTED",
    "FAILED_TERMINAL",
    "SWITCHED_TO_FALLBACK",
]

HERO_ENGINE = "FLOW_HERO_VIDEO"
STICKMAN_ENGINE = "CODE_STICKMAN"
STILL_ENGINE = "STILL_2K_PANZOOM"
AUDIO_ENGINE = "AUDIO_EVIDENCE_CARD"
FOIA_ENGINE = "FOIA_REAL_FOOTAGE"

HEADLESS_PROVIDER_ROUTES: frozenset[FlowBackendMode] = frozenset(
    {"GEMINI_OMNI_INTERACTIONS", "VERTEX_VEO_ENTERPRISE"}
)

FALLBACK_CANDIDATES: tuple[str, ...] = (
    STILL_ENGINE,
    STICKMAN_ENGINE,
    AUDIO_ENGINE,
    FOIA_ENGINE,
)

MOTIF_FOR_ENGINE: dict[str, str] = {
    STICKMAN_ENGINE: "StickmanStage",
    STILL_ENGINE: "Illustrative2KPanZoom",
    AUDIO_ENGINE: "AudioEvidenceCard",
    FOIA_ENGINE: "FoiaFootageFrame",
    HERO_ENGINE: "HeroVideoBridge",
}

DEFAULT_ENGINE_BY_ROUTE: dict[FlowBackendMode, str] = {
    "GEMINI_OMNI_INTERACTIONS": "gemini-omni-1.2-flash",
    "VERTEX_VEO_ENTERPRISE": "vertex-veo-enterprise",
    "HUMAN_BATCH_DESK": "manual-desk-video",
}


class DailyResetLockError(Exception):
    """Raised when Batch Desk dispatch is blocked before ``next_daily_reset_utc_ms``."""

    def __init__(self, account_id: str, now_ms: int, next_daily_reset_utc_ms: int) -> None:
        self.account_id = account_id
        self.now_ms = now_ms
        self.next_daily_reset_utc_ms = next_daily_reset_utc_ms
        super().__init__(
            f"DAILY_RESET_LOCK: account {account_id} locked until {next_daily_reset_utc_ms} "
            f"(now={now_ms})"
        )


class NeighborFallbackError(ValueError):
    """Raised when ``fallback_spec_json`` repeats a neighbor hero engine (RULE_05)."""


@dataclass(frozen=True, slots=True)
class AccountDailyLedger:
    """Rolling ``24h + 5m`` window fields mirrored from ``google_accounts``."""

    account_id: str
    daily_credits_left: int
    first_daily_spend_utc_ms: int
    next_daily_reset_utc_ms: int


@dataclass(frozen=True, slots=True)
class FallbackSpec:
    visual_engine: str
    motif_component: str
    reason: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "visual_engine": self.visual_engine,
                "motif_component": self.motif_component,
                "reason": self.reason,
            },
            sort_keys=True,
        )


@dataclass(frozen=True, slots=True)
class FlowJobRecord:
    """In-memory ``flow_jobs`` row before persistence."""

    flow_job_id: str
    episode_id: str
    scene_id: str
    idempotency_key: str
    provider_route: FlowBackendMode
    engine_model: str
    prompt_mode: VideoPromptMode
    prompt_v1: str
    prompt_v2_safe: str
    fallback_spec_json: FallbackSpec
    duration_bucket_sec: int
    estimated_micro_usd: int
    state: FlowJobState = "PENDING"
    assigned_account_id: str | None = None
    updated_at: int = 0


@dataclass(frozen=True, slots=True)
class FlowJobDispatch:
    """Minimal payload passed to ``dispatch_flow_jobs``."""

    flow_job_id: str
    episode_id: str
    scene_id: str
    idempotency_key: str
    provider_route: FlowBackendMode
    prompt_mode: VideoPromptMode
    prompt_v1: str
    prompt_v2_safe: str
    duration_bucket_sec: int


@dataclass(frozen=True, slots=True)
class FlowDispatchReceipt:
    flow_job_id: str
    provider_route: FlowBackendMode
    state: Literal["SUBMITTING", "QUEUED_BATCH_DESK"]


@dataclass(frozen=True, slots=True)
class FlowDispatchOutcome:
    episode_id: str
    provider_route: FlowBackendMode
    episode_state: str
    parked: bool
    dispatched: bool
    daily_reset_locked: bool
    flow_jobs: tuple[FlowJobRecord, ...]
    receipts: tuple[FlowDispatchReceipt, ...]


@runtime_checkable
class FlowDispatchPort(Protocol):
    """Injected render backend surface; Task 091 ``dispatch_flow_jobs`` seam."""

    def dispatch_flow_jobs(
        self,
        jobs: Sequence[FlowJobDispatch],
    ) -> tuple[FlowDispatchReceipt, ...]:
        """Submit or queue hero flow jobs. Implementations must not open sockets here."""


def compute_idempotency_key(
    episode_id: str,
    scene_id: str,
    prompt_v1: str,
    *,
    attempt: int = 1,
) -> str:
    """Deterministic ``sha256(episode + scene + prompt_hash + attempt)`` key."""

    prompt_hash = hashlib.sha256(prompt_v1.encode("utf-8")).hexdigest()
    raw = f"{episode_id}|{scene_id}|{prompt_hash}|{attempt}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def select_non_neighbor_fallback_engine(
    prev_engine: str | None,
    next_engine: str | None,
) -> str:
    """Pick a fallback engine distinct from both neighbors (RULE_05)."""

    if prev_engine == STICKMAN_ENGINE and next_engine == STICKMAN_ENGINE:
        return STILL_ENGINE
    forbidden = {e for e in (prev_engine, next_engine, HERO_ENGINE) if e}
    for candidate in FALLBACK_CANDIDATES:
        if candidate not in forbidden:
            return candidate
    return STILL_ENGINE


def build_neighbor_safe_fallback(
    *,
    prev_engine: str | None = None,
    next_engine: str | None = None,
    reason: str = "RULE_05 non-neighbor fallback",
) -> FallbackSpec:
    engine = select_non_neighbor_fallback_engine(prev_engine, next_engine)
    return FallbackSpec(
        visual_engine=engine,
        motif_component=MOTIF_FOR_ENGINE[engine],
        reason=reason,
    )


def assert_non_neighbor_fallback(
    fallback: FallbackSpec,
    *,
    prev_engine: str | None,
    next_engine: str | None,
) -> None:
    forbidden = {e for e in (prev_engine, next_engine, HERO_ENGINE) if e}
    if fallback.visual_engine in forbidden:
        raise NeighborFallbackError(
            f"fallback {fallback.visual_engine} collides with neighbors {forbidden}"
        )


def is_daily_reset_locked(*, now_ms: int, next_daily_reset_utc_ms: int) -> bool:
    """True when ``now`` is still inside the rolling ``24h + 5m`` lockout window."""

    if next_daily_reset_utc_ms <= 0:
        return False
    return now_ms < next_daily_reset_utc_ms


def next_reset_from_first_spend(first_daily_spend_utc_ms: int) -> int:
    return first_daily_spend_utc_ms + DAILY_RESET_WINDOW_MS


@dataclass
class FlowBatchParker:
    """Stage flow jobs and dispatch or park by backend mode."""

    port: FlowDispatchPort
    now_ms: int
    headless: bool = True

    def create_flow_job(
        self,
        *,
        flow_job_id: str,
        episode_id: str,
        scene_id: str,
        prompt_mode: VideoPromptMode,
        prompt_v1: str,
        prompt_v2_safe: str,
        provider_route: FlowBackendMode,
        duration_bucket_sec: int = 8,
        estimated_micro_usd: int = 0,
        prev_neighbor_engine: str | None = None,
        next_neighbor_engine: str | None = None,
        fallback: FallbackSpec | None = None,
        assigned_account_id: str | None = None,
        attempt: int = 1,
    ) -> FlowJobRecord:
        """Build one neighbor-safe ``flow_jobs`` record (unique episode + scene)."""

        fallback_spec = fallback or build_neighbor_safe_fallback(
            prev_engine=prev_neighbor_engine,
            next_engine=next_neighbor_engine,
        )
        assert_non_neighbor_fallback(
            fallback_spec,
            prev_engine=prev_neighbor_engine,
            next_engine=next_neighbor_engine,
        )
        return FlowJobRecord(
            flow_job_id=flow_job_id,
            episode_id=episode_id,
            scene_id=scene_id,
            idempotency_key=compute_idempotency_key(
                episode_id, scene_id, prompt_v1, attempt=attempt
            ),
            provider_route=provider_route,
            engine_model=DEFAULT_ENGINE_BY_ROUTE[provider_route],
            prompt_mode=prompt_mode,
            prompt_v1=prompt_v1,
            prompt_v2_safe=prompt_v2_safe,
            fallback_spec_json=fallback_spec,
            duration_bucket_sec=duration_bucket_sec,
            estimated_micro_usd=estimated_micro_usd,
            assigned_account_id=assigned_account_id,
            updated_at=self.now_ms,
        )

    def dispatch_or_park(
        self,
        *,
        episode_id: str,
        provider_route: FlowBackendMode,
        jobs: Sequence[FlowJobRecord],
        account: AccountDailyLedger | None = None,
        episode_state: str = "CODE_RENDERED",
    ) -> FlowDispatchOutcome:
        """Headless routes dispatch immediately; Batch Desk parks or locks."""

        if provider_route in HEADLESS_PROVIDER_ROUTES or self.headless:
            return self._dispatch_headless(episode_id, provider_route, jobs, episode_state)

        if provider_route != "HUMAN_BATCH_DESK":
            raise ValueError(f"unsupported provider_route: {provider_route}")

        locked = account is not None and is_daily_reset_locked(
            now_ms=self.now_ms,
            next_daily_reset_utc_ms=account.next_daily_reset_utc_ms,
        )
        if locked:
            assert account is not None
            raise DailyResetLockError(
                account.account_id,
                self.now_ms,
                account.next_daily_reset_utc_ms,
            )

        parked_state = AWAITING_FLOW_BATCH
        dispatch_jobs = [_to_dispatch(row) for row in jobs]
        receipts = self.port.dispatch_flow_jobs(dispatch_jobs)
        return FlowDispatchOutcome(
            episode_id=episode_id,
            provider_route=provider_route,
            episode_state=parked_state,
            parked=True,
            dispatched=True,
            daily_reset_locked=False,
            flow_jobs=tuple(jobs),
            receipts=receipts,
        )

    def try_batch_desk_dispatch(
        self,
        *,
        episode_id: str,
        jobs: Sequence[FlowJobRecord],
        account: AccountDailyLedger,
        episode_state: str = AWAITING_FLOW_BATCH,
    ) -> FlowDispatchOutcome:
        """Dispatch parked Batch Desk jobs when the account tab is unlocked."""

        if self.headless:
            raise ValueError("headless mode must not run HUMAN_BATCH_DESK dispatch")

        if is_daily_reset_locked(
            now_ms=self.now_ms,
            next_daily_reset_utc_ms=account.next_daily_reset_utc_ms,
        ):
            raise DailyResetLockError(
                account.account_id,
                self.now_ms,
                account.next_daily_reset_utc_ms,
            )

        receipts = self.port.dispatch_flow_jobs([_to_dispatch(row) for row in jobs])
        return FlowDispatchOutcome(
            episode_id=episode_id,
            provider_route="HUMAN_BATCH_DESK",
            episode_state=episode_state,
            parked=True,
            dispatched=True,
            daily_reset_locked=False,
            flow_jobs=tuple(jobs),
            receipts=receipts,
        )

    def _dispatch_headless(
        self,
        episode_id: str,
        provider_route: FlowBackendMode,
        jobs: Sequence[FlowJobRecord],
        episode_state: str,
    ) -> FlowDispatchOutcome:
        dispatch_jobs = [_to_dispatch(row) for row in jobs]
        submitting: list[FlowJobRecord] = []
        for row in jobs:
            submitting.append(
                FlowJobRecord(
                    flow_job_id=row.flow_job_id,
                    episode_id=row.episode_id,
                    scene_id=row.scene_id,
                    idempotency_key=row.idempotency_key,
                    provider_route=row.provider_route,
                    engine_model=row.engine_model,
                    prompt_mode=row.prompt_mode,
                    prompt_v1=row.prompt_v1,
                    prompt_v2_safe=row.prompt_v2_safe,
                    fallback_spec_json=row.fallback_spec_json,
                    duration_bucket_sec=row.duration_bucket_sec,
                    estimated_micro_usd=row.estimated_micro_usd,
                    state="SUBMITTING",
                    assigned_account_id=row.assigned_account_id,
                    updated_at=self.now_ms,
                )
            )
        receipts = self.port.dispatch_flow_jobs(dispatch_jobs)
        return FlowDispatchOutcome(
            episode_id=episode_id,
            provider_route=provider_route,
            episode_state=episode_state,
            parked=False,
            dispatched=True,
            daily_reset_locked=False,
            flow_jobs=tuple(submitting),
            receipts=receipts,
        )


def _to_dispatch(row: FlowJobRecord) -> FlowJobDispatch:
    return FlowJobDispatch(
        flow_job_id=row.flow_job_id,
        episode_id=row.episode_id,
        scene_id=row.scene_id,
        idempotency_key=row.idempotency_key,
        provider_route=row.provider_route,
        prompt_mode=row.prompt_mode,
        prompt_v1=row.prompt_v1,
        prompt_v2_safe=row.prompt_v2_safe,
        duration_bucket_sec=row.duration_bucket_sec,
    )


def flow_job_unique_key(row: FlowJobRecord | Mapping[str, object]) -> tuple[str, str]:
    if isinstance(row, FlowJobRecord):
        return (row.episode_id, row.scene_id)
    return (str(row["episode_id"]), str(row["scene_id"]))