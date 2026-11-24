"""Layer 1 director-manifest@4 proposal generator (Task 075).

Builds a 1,200 second ProductionManifest and TimelineSpec rows from approved
scene plans aligned to a segmented voice manifest, including a flexible
210s–270s CaseBoardSpine boundary snap that never cuts an in-progress FOIA slot.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Sequence

from shared_contracts.models import (
    ProductionManifest,
    ScenePlan,
    TimelineSpec,
    VideoPromptMode,
    VoiceTrackManifest,
)

TARGET_DURATION_MS = 1_200_000
CODE_FOIA_MS = 780_000
STILL_2K_MS = 340_000
HERO_MS = 80_000
MAX_HERO_CLIPS = 10
MAX_HERO_DURATION_SEC = 80
CASE_BOARD_WINDOW_START_MS = 210_000
CASE_BOARD_WINDOW_END_MS = 270_000
FPS: Literal[30] = 30

_CODE_FOIA_ENGINES = frozenset({"CODE_STICKMAN", "FOIA_REAL_FOOTAGE", "AUDIO_EVIDENCE_CARD"})
_STILL_2K_ENGINES = frozenset({"STILL_2K_PANZOOM"})
_HERO_ENGINES = frozenset({"FLOW_HERO_VIDEO"})
_VIDEO_PROMPT_MODES = frozenset({"TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"})
_MVP_MOTIFS = frozenset(
    {"StickmanStage", "AudioEvidenceCard", "RedactedDocReveal", "FoiaFootageFrame"}
)


class ManifestProposerError(ValueError):
    """Raised when approved scene plans violate manifest invariants."""


@dataclass(frozen=True)
class ManifestProposal:
    production_manifest: ProductionManifest
    timeline_specs: tuple[TimelineSpec, ...]
    case_board_spine_at_ms: int


def propose_manifest(
    *,
    manifest_id: str,
    episode_id: str,
    case_id: str,
    cold_open_archetype: str,
    flow_backend_mode: str,
    scene_plans: Sequence[ScenePlan],
    voice: VoiceTrackManifest,
) -> ManifestProposal:
    """Compile ProductionManifest + hero TimelineSpec rows from approved plans."""
    approved = _approved_scene_plans(scene_plans)
    if not approved:
        raise ManifestProposerError("at least one PLAN_APPROVED scene plan is required")
    if voice.episode_id != episode_id:
        raise ManifestProposerError("voice manifest episode_id must match the proposal episode_id")

    _assert_voice_alignment(voice)
    hero_plans = [plan for plan in approved if plan.visual_engine in _HERO_ENGINES]
    _assert_hero_caps(hero_plans)

    split = _measure_runtime_split_ms(approved)
    _assert_honest_split(split)

    spine_at_ms = resolve_case_board_spine_at_ms(voice, approved)
    timeline_specs = tuple(_hero_timeline_specs(approved, episode_id))

    hero_duration_ms = sum(plan.timing_end_ms - plan.timing_start_ms for plan in hero_plans)
    manifest = ProductionManifest(
        manifest_id=manifest_id,
        episode_id=episode_id,
        case_id=case_id,
        fps=FPS,
        cold_open_archetype=cold_open_archetype,  # type: ignore[arg-type]
        flow_backend_mode=flow_backend_mode,  # type: ignore[arg-type]
        target_duration_ms=TARGET_DURATION_MS,
        code_foia_ms=CODE_FOIA_MS,
        still_2k_ms=STILL_2K_MS,
        hero_ms=HERO_MS,
        max_hero_clips=MAX_HERO_CLIPS,
        max_hero_duration_sec=MAX_HERO_DURATION_SEC,
        hero_clip_count=len(hero_plans),
        hero_duration_sec=hero_duration_ms // 1000,
        scene_plan_ids=[plan.scene_plan_id for plan in approved],
        voice_total_master_ms=voice.total_master_ms,
        timeline_validated_sha256=_timeline_sha256(timeline_specs, spine_at_ms),
    )
    return ManifestProposal(
        production_manifest=manifest,
        timeline_specs=timeline_specs,
        case_board_spine_at_ms=spine_at_ms,
    )


def resolve_case_board_spine_at_ms(
    voice: VoiceTrackManifest,
    scene_plans: Sequence[ScenePlan],
) -> int:
    """Pick a completed boundary inside 210s–270s, snapping past in-flight FOIA audio."""
    raw = _collect_spine_boundary_candidates(voice, scene_plans)
    if not raw:
        raise ManifestProposerError("no CaseBoardSpine boundary candidate in 210s–270s window")

    adjusted = {_snap_boundary_across_foia(ms, voice) for ms in raw}
    in_window = sorted(
        ms
        for ms in adjusted
        if CASE_BOARD_WINDOW_START_MS <= ms <= CASE_BOARD_WINDOW_END_MS
    )
    if not in_window:
        raise ManifestProposerError("CaseBoardSpine snap fell outside 210s–270s window")
    return in_window[-1]


def _approved_scene_plans(scene_plans: Sequence[ScenePlan]) -> list[ScenePlan]:
    return sorted(
        (
            plan
            for plan in scene_plans
            if plan.plan_status in {"PLAN_APPROVED", "EDITED_APPROVED"}
        ),
        key=lambda plan: plan.seq_index,
    )


def _assert_voice_alignment(voice: VoiceTrackManifest) -> None:
    if abs(voice.total_master_ms - TARGET_DURATION_MS) > 250:
        raise ManifestProposerError("voice total_master_ms must be within 250 ms of 1200s")


def _assert_hero_caps(hero_plans: Sequence[ScenePlan]) -> None:
    if len(hero_plans) > MAX_HERO_CLIPS:
        raise ManifestProposerError("hero clip count exceeds max_hero_clips")
    hero_ms = sum(plan.timing_end_ms - plan.timing_start_ms for plan in hero_plans)
    if hero_ms > MAX_HERO_DURATION_SEC * 1000:
        raise ManifestProposerError("hero runtime exceeds max_hero_duration_sec")
    for plan in hero_plans:
        if plan.prompt_mode not in _VIDEO_PROMPT_MODES:
            raise ManifestProposerError("hero scenes require a video prompt_mode")
        duration = plan.timing_end_ms - plan.timing_start_ms
        if plan.prompt_mode == "FIRST_AND_LAST_FRAME" and duration > 10_000:
            raise ManifestProposerError("FIRST_AND_LAST_FRAME hero clips must be <= 10s")


def _measure_runtime_split_ms(scene_plans: Sequence[ScenePlan]) -> dict[str, int]:
    code = still = hero = 0
    for plan in scene_plans:
        duration = plan.timing_end_ms - plan.timing_start_ms
        if plan.visual_engine in _CODE_FOIA_ENGINES:
            code += duration
        elif plan.visual_engine in _STILL_2K_ENGINES:
            still += duration
        elif plan.visual_engine in _HERO_ENGINES:
            hero += duration
        else:
            raise ManifestProposerError(f"unsupported visual_engine {plan.visual_engine}")
    return {"code_foia_ms": code, "still_2k_ms": still, "hero_ms": hero}


def _assert_honest_split(split: dict[str, int]) -> None:
    total = split["code_foia_ms"] + split["still_2k_ms"] + split["hero_ms"]
    if total != TARGET_DURATION_MS:
        raise ManifestProposerError("scene plan durations must sum to 1200s")
    if split != {"code_foia_ms": CODE_FOIA_MS, "still_2k_ms": STILL_2K_MS, "hero_ms": HERO_MS}:
        raise ManifestProposerError("runtime split must be 780s code/FOIA, 340s 2K, 80s hero")


def _collect_spine_boundary_candidates(
    voice: VoiceTrackManifest,
    scene_plans: Sequence[ScenePlan],
) -> set[int]:
    candidates: set[int] = set()
    for plan in scene_plans:
        if CASE_BOARD_WINDOW_START_MS <= plan.timing_end_ms <= CASE_BOARD_WINDOW_END_MS:
            candidates.add(plan.timing_end_ms)
    for segment in voice.segments:
        if segment.segment_kind == "FOIA_AUDIO_SLOT":
            end_ms = segment.end_ms
            if CASE_BOARD_WINDOW_START_MS <= end_ms <= CASE_BOARD_WINDOW_END_MS:
                candidates.add(end_ms)
    for stamp in voice.word_timestamps:
        if CASE_BOARD_WINDOW_START_MS <= stamp.end_ms <= CASE_BOARD_WINDOW_END_MS:
            candidates.add(stamp.end_ms)
    return candidates


def _snap_boundary_across_foia(at_ms: int, voice: VoiceTrackManifest) -> int:
    for segment in voice.segments:
        if segment.segment_kind != "FOIA_AUDIO_SLOT":
            continue
        if segment.start_ms < at_ms < segment.end_ms:
            return segment.end_ms
    return at_ms


def _hero_timeline_specs(
    scene_plans: Sequence[ScenePlan],
    episode_id: str,
) -> list[TimelineSpec]:
    specs: list[TimelineSpec] = []
    for plan in scene_plans:
        if plan.visual_engine not in _HERO_ENGINES:
            continue
        mode = plan.prompt_mode
        if mode not in _VIDEO_PROMPT_MODES:
            continue
        duration_ms = plan.timing_end_ms - plan.timing_start_ms
        start_sha, end_sha = _keyframe_hashes(plan)
        motif = _timeline_motif(plan)
        specs.append(
            TimelineSpec(
                episode_id=episode_id,
                scene_id=plan.scene_id,
                scene_plan_id=plan.scene_plan_id,
                fps=FPS,
                motif_component=motif,  # type: ignore[arg-type]
                prompt_mode=mode,  # type: ignore[arg-type]
                duration_ms=duration_ms,
                start_frame_sha256=start_sha,
                end_frame_sha256=end_sha,
            )
        )
    return specs


def _timeline_motif(plan: ScenePlan) -> str:
    if plan.motif_component in _MVP_MOTIFS:
        return plan.motif_component
    return "StickmanStage"


def _keyframe_hashes(plan: ScenePlan) -> tuple[str | None, str | None]:
    start: str | None = None
    end: str | None = None
    for ref in plan.keyframe_refs_json:
        if ref.role == "START":
            start = ref.sha256
        elif ref.role == "END":
            end = ref.sha256
    return start, end


def _timeline_sha256(
    timeline_specs: Sequence[TimelineSpec],
    case_board_spine_at_ms: int,
) -> str:
    payload = {
        "case_board_spine_at_ms": case_board_spine_at_ms,
        "timeline_specs": [spec.model_dump(mode="json") for spec in timeline_specs],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()