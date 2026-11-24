"""Offline RenderBackendStub for Part 1 vertical-slice tests. No network."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import ValidationError

from shared_contracts.models import (
    CaseBible,
    ProductionManifest,
    ScenePlan,
    TimelineSpec,
    VoiceTrackManifest,
)

FlowBackendMode = Literal[
    "GEMINI_OMNI_INTERACTIONS",
    "VERTEX_VEO_ENTERPRISE",
    "HUMAN_BATCH_DESK",
]
VideoPromptMode = Literal["TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]
SpendPurpose = Literal["PRODUCTION", "LIVE_SANDBOX", "OFFLINE_TEST"]

POOL_SOURCES = ("GEMINI_API_USD", "VERTEX_USD", "DAILY_CREDITS", "MONTHLY_CREDITS")
CRASH_STATES = ("SUBMITTING", "RUNNING", "UNKNOWN_RECONCILE")
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
DAILY_RESET_BUFFER_MS = 86_400_000 + 300_000
BACKEND_NAME = "render-backend-stub-offline"


class OfflineTestSpendError(ValueError):
    """OFFLINE_TEST reservations must carry $0 estimated spend."""


class BatchDeskLockedError(RuntimeError):
    """HUMAN_BATCH_DESK refused: account tab is locked until daily reset."""


class FlowJobNotFound(LookupError):
    """No matching ``flow_jobs`` row."""


@dataclass(frozen=True, slots=True)
class ValidatedRenderBundle:
    manifest: ProductionManifest
    timeline: TimelineSpec
    case_bible: CaseBible
    scene_plan: ScenePlan
    voice_manifest: VoiceTrackManifest


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    account_id: str
    daily_credits_left: int
    next_daily_reset_utc_ms: int
    daily_credits_cap: int = 50
    first_daily_spend_utc_ms: int = 0


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class CodeSceneRequest:
    episode_id: str
    scene_id: str
    motif_component: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class PanZoom2KRequest:
    episode_id: str
    scene_id: str
    still_asset_relpath: str
    duration_ms: int
    span_cols: float = 2.0
    span_rows: float = 2.0


@dataclass(frozen=True, slots=True)
class RenderSceneReceipt:
    backend_name: str
    episode_id: str
    scene_id: str
    output_relpath: str
    sha256: str
    fps: Literal[30] = 30


@dataclass(frozen=True, slots=True)
class FlowKeyframeRef:
    ref_id: str
    role: Literal["START", "END"]
    png_relpath: str
    sha256: str


@dataclass(frozen=True, slots=True)
class FlowKeyframeSet:
    flow_job_id: str
    prompt_mode: VideoPromptMode
    keyframes: tuple[FlowKeyframeRef, ...]


@dataclass(frozen=True, slots=True)
class FlowJobDispatch:
    flow_job_id: str
    episode_id: str
    scene_id: str
    idempotency_key: str
    provider_route: FlowBackendMode
    prompt_mode: VideoPromptMode
    prompt_v1: str
    prompt_v2_safe: str
    duration_bucket_sec: int
    estimated_micro_usd: int = 0
    estimated_credits: int = 0


@dataclass(frozen=True, slots=True)
class FlowJobDispatchReceipt:
    flow_job_id: str
    provider_route: FlowBackendMode
    state: Literal["PENDING", "SUBMITTING", "QUEUED_BATCH_DESK"]
    estimated_micro_usd: int


@dataclass(frozen=True, slots=True)
class MasterAssemblyRequest:
    manifest_id: str
    episode_id: str
    scene_receipts: tuple[RenderSceneReceipt, ...]
    target_lufs: float = -14.0


@dataclass(frozen=True, slots=True)
class MasterAssemblyReceipt:
    episode_id: str
    manifest_id: str
    final_mp4_relpath: str
    integrated_lufs: float
    scene_count: int
    sha256: str


@dataclass(frozen=True, slots=True)
class VerticalSliceResult:
    backend_name: str
    episode_id: str
    manifest_id: str
    scene_id: str
    bundle_sha256: str
    scene_relpath: str
    master_relpath: str
    flow_dispatch_state: str
    spend_micro_usd: int


def _stable_digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def validate_render_bundle(
    manifest: Mapping[str, Any],
    timeline: Mapping[str, Any],
    case_bible: Mapping[str, Any],
    scene_plan: Mapping[str, Any],
    voice_manifest: Mapping[str, Any],
) -> ValidatedRenderBundle:
    """Parse the five upstream dicts; unknown keys are rejected by ContractModel."""

    try:
        return ValidatedRenderBundle(
            manifest=ProductionManifest.model_validate(manifest),
            timeline=TimelineSpec.model_validate(timeline),
            case_bible=CaseBible.model_validate(case_bible),
            scene_plan=ScenePlan.model_validate(scene_plan),
            voice_manifest=VoiceTrackManifest.model_validate(voice_manifest),
        )
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def assert_offline_test_spend(purpose: SpendPurpose, estimated_micro_usd: int) -> None:
    if purpose == "OFFLINE_TEST" and estimated_micro_usd != 0:
        raise OfflineTestSpendError(
            "OFFLINE_TEST_ZERO_SPEND: Ordinary tests must use transport mocks with "
            "$0 estimated spend"
        )


def batch_desk_may_spend(account: AccountSnapshot, now_ms: int, credits: int) -> bool:
    """Mirror ``atomic_refill_and_reserve_daily_account_credits`` lock predicate."""

    if credits <= 0:
        return True
    if account.next_daily_reset_utc_ms == 0 or now_ms >= account.next_daily_reset_utc_ms:
        return credits <= account.daily_credits_cap
    return now_ms < account.next_daily_reset_utc_ms and account.daily_credits_left >= credits


def ensure_batch_desk_unlocked(account: AccountSnapshot, now_ms: int, credits: int) -> None:
    if not batch_desk_may_spend(account, now_ms, credits):
        raise BatchDeskLockedError(
            f"account {account.account_id} locked until "
            f"next_daily_reset_utc_ms={account.next_daily_reset_utc_ms}"
        )


def next_daily_reset_after_first_spend(first_spend_utc_ms: int) -> int:
    return first_spend_utc_ms + DAILY_RESET_BUFFER_MS


class LocalFlowJobRepository:
    """In-worktree flow-job ledger matching Task 011 SQLite semantics."""

    def __init__(self, pipeline_db: str | Path, *, busy_timeout_ms: int = 5_000) -> None:
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


@runtime_checkable
class RenderBackendPort(Protocol):
    def render_code_scene(self, request: CodeSceneRequest) -> RenderSceneReceipt: ...

    def render_2k_panzoom(self, request: PanZoom2KRequest) -> RenderSceneReceipt: ...

    def generate_flow_keyframes(
        self,
        flow_job_id: str,
        prompt_mode: VideoPromptMode,
        visual_prompt: str,
    ) -> FlowKeyframeSet: ...

    def dispatch_flow_jobs(
        self,
        jobs: Sequence[FlowJobDispatch],
        *,
        now_ms: int,
        batch_account: AccountSnapshot | None = None,
    ) -> tuple[FlowJobDispatchReceipt, ...]: ...

    def assemble_master(self, request: MasterAssemblyRequest) -> MasterAssemblyReceipt: ...


@dataclass
class RenderBackendStub:
    """Deterministic offline backend for manifest-to-master slice tests."""

    spend_purpose: SpendPurpose = "OFFLINE_TEST"
    pipeline_db: Path | None = None
    backend_name: str = BACKEND_NAME

    @property
    def flow_jobs(self) -> LocalFlowJobRepository | None:
        if self.pipeline_db is None:
            return None
        return LocalFlowJobRepository(self.pipeline_db)

    def validate_bundle(
        self,
        manifest: Mapping[str, Any],
        timeline: Mapping[str, Any],
        case_bible: Mapping[str, Any],
        scene_plan: Mapping[str, Any],
        voice_manifest: Mapping[str, Any],
    ) -> ValidatedRenderBundle:
        bundle = validate_render_bundle(
            manifest, timeline, case_bible, scene_plan, voice_manifest
        )
        if bundle.manifest.episode_id != bundle.timeline.episode_id:
            raise ValueError("manifest episode_id must match timeline episode_id")
        if bundle.case_bible.episode_id != bundle.manifest.episode_id:
            raise ValueError("case_bible episode_id must match manifest episode_id")
        if bundle.scene_plan.episode_id != bundle.manifest.episode_id:
            raise ValueError("scene_plan episode_id must match manifest episode_id")
        if bundle.voice_manifest.episode_id != bundle.manifest.episode_id:
            raise ValueError("voice_manifest episode_id must match manifest episode_id")
        return bundle

    def bundle_digest(self, bundle: ValidatedRenderBundle) -> str:
        parts = (
            bundle.manifest.model_dump_json(),
            bundle.timeline.model_dump_json(),
            bundle.case_bible.model_dump_json(),
            bundle.scene_plan.model_dump_json(),
            bundle.voice_manifest.model_dump_json(),
        )
        return _stable_digest(*parts)

    def complete_vertical_slice(
        self,
        manifest: Mapping[str, Any],
        timeline: Mapping[str, Any],
        case_bible: Mapping[str, Any],
        scene_plan: Mapping[str, Any],
        voice_manifest: Mapping[str, Any],
        *,
        now_ms: int,
        flow_jobs: Sequence[FlowJobDispatch] = (),
        batch_account: AccountSnapshot | None = None,
    ) -> VerticalSliceResult:
        bundle = self.validate_bundle(
            manifest, timeline, case_bible, scene_plan, voice_manifest
        )
        digest = self.bundle_digest(bundle)
        scene = self.render_code_scene(
            CodeSceneRequest(
                episode_id=bundle.manifest.episode_id,
                scene_id=bundle.timeline.scene_id,
                motif_component=bundle.scene_plan.motif_component,
                duration_ms=bundle.timeline.duration_ms,
            )
        )
        dispatch_state = "SKIPPED"
        if flow_jobs:
            receipts = self.dispatch_flow_jobs(
                flow_jobs, now_ms=now_ms, batch_account=batch_account
            )
            dispatch_state = receipts[0].state if receipts else dispatch_state
        master = self.assemble_master(
            MasterAssemblyRequest(
                manifest_id=bundle.manifest.manifest_id,
                episode_id=bundle.manifest.episode_id,
                scene_receipts=(scene,),
            )
        )
        return VerticalSliceResult(
            backend_name=self.backend_name,
            episode_id=bundle.manifest.episode_id,
            manifest_id=bundle.manifest.manifest_id,
            scene_id=bundle.timeline.scene_id,
            bundle_sha256=digest,
            scene_relpath=scene.output_relpath,
            master_relpath=master.final_mp4_relpath,
            flow_dispatch_state=dispatch_state,
            spend_micro_usd=0,
        )

    def record_flow_attempt(self, **kwargs: Any) -> FlowAttemptResult:
        repo = self.flow_jobs
        if repo is None:
            raise RuntimeError("pipeline_db is required for flow attempt recording")
        return repo.record_attempt(**kwargs)

    def render_code_scene(self, request: CodeSceneRequest) -> RenderSceneReceipt:
        digest = _stable_digest(
            self.backend_name,
            "code",
            request.episode_id,
            request.scene_id,
            request.motif_component,
            str(request.duration_ms),
        )
        return RenderSceneReceipt(
            backend_name=self.backend_name,
            episode_id=request.episode_id,
            scene_id=request.scene_id,
            output_relpath=(
                f"stub/{request.episode_id}/{request.scene_id}_{request.motif_component}.mp4"
            ),
            sha256=digest,
        )

    def render_2k_panzoom(self, request: PanZoom2KRequest) -> RenderSceneReceipt:
        digest = _stable_digest(
            self.backend_name,
            "2k",
            request.still_asset_relpath,
            request.scene_id,
            str(request.duration_ms),
        )
        return RenderSceneReceipt(
            backend_name=self.backend_name,
            episode_id=request.episode_id,
            scene_id=request.scene_id,
            output_relpath=f"stub/{request.episode_id}/{request.scene_id}_2k.mp4",
            sha256=digest,
        )

    def generate_flow_keyframes(
        self,
        flow_job_id: str,
        prompt_mode: VideoPromptMode,
        visual_prompt: str,
    ) -> FlowKeyframeSet:
        digest = _stable_digest(self.backend_name, flow_job_id, prompt_mode, visual_prompt)
        keyframes: list[FlowKeyframeRef] = [
            FlowKeyframeRef(
                ref_id=f"{flow_job_id}_start",
                role="START",
                png_relpath=f"stub/keyframes/{flow_job_id}/start.png",
                sha256=digest,
            )
        ]
        if prompt_mode == "FIRST_AND_LAST_FRAME":
            keyframes.append(
                FlowKeyframeRef(
                    ref_id=f"{flow_job_id}_end",
                    role="END",
                    png_relpath=f"stub/keyframes/{flow_job_id}/end.png",
                    sha256=_stable_digest(digest, "end"),
                )
            )
        return FlowKeyframeSet(
            flow_job_id=flow_job_id,
            prompt_mode=prompt_mode,
            keyframes=tuple(keyframes),
        )

    def dispatch_flow_jobs(
        self,
        jobs: Sequence[FlowJobDispatch],
        *,
        now_ms: int,
        batch_account: AccountSnapshot | None = None,
    ) -> tuple[FlowJobDispatchReceipt, ...]:
        receipts: list[FlowJobDispatchReceipt] = []
        for job in jobs:
            assert_offline_test_spend(self.spend_purpose, job.estimated_micro_usd)
            if job.provider_route == "HUMAN_BATCH_DESK":
                credits = job.estimated_credits if job.estimated_credits > 0 else 1
                if batch_account is None:
                    raise BatchDeskLockedError(
                        "HUMAN_BATCH_DESK dispatch requires an account snapshot"
                    )
                ensure_batch_desk_unlocked(batch_account, now_ms, credits)
                state: Literal["PENDING", "SUBMITTING", "QUEUED_BATCH_DESK"] = (
                    "QUEUED_BATCH_DESK"
                )
            else:
                state = "PENDING"
            receipts.append(
                FlowJobDispatchReceipt(
                    flow_job_id=job.flow_job_id,
                    provider_route=job.provider_route,
                    state=state,
                    estimated_micro_usd=0 if self.spend_purpose == "OFFLINE_TEST" else job.estimated_micro_usd,
                )
            )
        return tuple(receipts)

    def assemble_master(self, request: MasterAssemblyRequest) -> MasterAssemblyReceipt:
        digest = _stable_digest(
            self.backend_name,
            request.manifest_id,
            request.episode_id,
            *(receipt.sha256 for receipt in request.scene_receipts),
        )
        return MasterAssemblyReceipt(
            episode_id=request.episode_id,
            manifest_id=request.manifest_id,
            final_mp4_relpath=f"stub/masters/{request.episode_id}/final_1080p30.mp4",
            integrated_lufs=request.target_lufs,
            scene_count=len(request.scene_receipts),
            sha256=digest,
        )