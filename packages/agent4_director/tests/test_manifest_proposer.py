"""Tests for Task 075 manifest proposer."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from agent4_director.manifest_proposer import (
    CODE_FOIA_MS,
    HERO_MS,
    STILL_2K_MS,
    TARGET_DURATION_MS,
    ManifestProposerError,
    propose_manifest,
    resolve_case_board_spine_at_ms,
)
from shared_contracts.models import (
    AcceptanceCriterion,
    KeyframeRef,
    ScenePlan,
    TransitionSpec,
    VoiceSegment,
    VoiceTrackManifest,
    WordTimestamp,
)

SHA = "a" * 64


def _criterion(cid: str = "crit_1") -> AcceptanceCriterion:
    return AcceptanceCriterion(
        criterion_id=cid,
        kind="SEMANTIC",
        text="Matches approved narration without misleading the viewer.",
    )


def _scene_plan(
    *,
    scene_plan_id: str,
    scene_id: str,
    seq_index: int,
    engine: str,
    motif: str,
    prompt_mode: str,
    start_ms: int,
    end_ms: int,
    keyframes: list | None = None,
    status: str = "PLAN_APPROVED",
) -> ScenePlan:
    return ScenePlan(
        scene_plan_id=scene_plan_id,
        episode_id="ep_test",
        scene_id=scene_id,
        seq_index=seq_index,
        story_purpose="Test beat",
        intended_audience_effect="Orient the viewer",
        approved_narration_text="According to the record, this beat occurred.",
        narration_version_sha256=SHA,
        cited_fact_ids_json=["fact_1"],
        visual_concept="Charcoal documentary plate",
        visual_engine=engine,  # type: ignore[arg-type]
        motif_component=motif,  # type: ignore[arg-type]
        prompt_mode=prompt_mode,  # type: ignore[arg-type]
        visual_prompt="Monochrome charcoal, no graphic injury",
        keyframe_refs_json=keyframes or [],
        expected_output_summary=f"{motif} from {start_ms} to {end_ms} ms",
        timing_start_ms=start_ms,
        timing_end_ms=end_ms,
        transition_spec_json=TransitionSpec(transition_type="CUT", duration_ms=0),
        edit_instructions="Hold in the safe zone",
        acceptance_criteria_json=[_criterion()],
        plan_status=status,  # type: ignore[arg-type]
        reviewed_by="editor_1",
        reviewed_at=100,
        created_at=50,
        updated_at=60,
    )


def _voice(
    *,
    segments: list[VoiceSegment],
    word_timestamps: list | None = None,
) -> VoiceTrackManifest:
    return VoiceTrackManifest(
        episode_id="ep_test",
        total_master_ms=TARGET_DURATION_MS,
        segments=segments,
        word_timestamps=word_timestamps or [],
    )


def _full_twenty_minute_plans() -> list[ScenePlan]:
    plans = [
        _scene_plan(
            scene_plan_id="plan_code",
            scene_id="scene_code",
            seq_index=1,
            engine="CODE_STICKMAN",
            motif="StickmanStage",
            prompt_mode="NONE",
            start_ms=0,
            end_ms=CODE_FOIA_MS,
        ),
        _scene_plan(
            scene_plan_id="plan_still",
            scene_id="scene_still",
            seq_index=2,
            engine="STILL_2K_PANZOOM",
            motif="Illustrative2KPanZoom",
            prompt_mode="NONE",
            start_ms=CODE_FOIA_MS,
            end_ms=CODE_FOIA_MS + STILL_2K_MS,
        ),
    ]
    hero_start = CODE_FOIA_MS + STILL_2K_MS
    hero_chunk = HERO_MS // 10
    for index in range(10):
        start = hero_start + index * hero_chunk
        end = start + hero_chunk
        mode = "TEXT_TO_VIDEO" if index % 3 == 0 else "FIRST_FRAME" if index % 3 == 1 else "FIRST_AND_LAST_FRAME"
        keyframes = []
        if mode == "FIRST_FRAME":
            keyframes = [KeyframeRef(ref_id=f"kf_{index}", role="START", sha256=SHA)]
        elif mode == "FIRST_AND_LAST_FRAME":
            keyframes = [
                KeyframeRef(ref_id=f"kf_{index}a", role="START", sha256=SHA),
                KeyframeRef(ref_id=f"kf_{index}b", role="END", sha256=SHA),
            ]
        plans.append(
            _scene_plan(
                scene_plan_id=f"plan_hero_{index}",
                scene_id=f"scene_hero_{index}",
                seq_index=3 + index,
                engine="FLOW_HERO_VIDEO",
                motif="HeroVideoBridge",
                prompt_mode=mode,
                start_ms=start,
                end_ms=end,
                keyframes=keyframes,
            )
        )
    return plans


def test_spine_snaps_to_911_slot_end_not_mid_call_scene_cut() -> None:
    scenes = [
      _scene_plan(
          scene_plan_id="plan_pre",
          scene_id="scene_pre",
          seq_index=1,
          engine="FOIA_REAL_FOOTAGE",
          motif="FoiaFootageFrame",
          prompt_mode="NONE",
          start_ms=180_000,
          end_ms=230_000,
      ),
      _scene_plan(
          scene_plan_id="plan_mid",
          scene_id="scene_mid",
          seq_index=2,
          engine="AUDIO_EVIDENCE_CARD",
          motif="AudioEvidenceCard",
          prompt_mode="NONE",
          start_ms=230_000,
          end_ms=240_000,
      ),
    ]
    voice = _voice(
        segments=[
            VoiceSegment(
                segment_id="seg_pre",
                episode_id="ep_test",
                seq_index=1,
                segment_kind="NARRATION",
                start_ms=0,
                end_ms=180_000,
                audio_path="audio/pre.wav",
                narration_version_sha256=SHA,
            ),
            VoiceSegment(
                segment_id="seg_911",
                episode_id="ep_test",
                seq_index=2,
                segment_kind="FOIA_AUDIO_SLOT",
                start_ms=230_000,
                end_ms=255_000,
                foia_asset_id="foia_911",
            ),
            VoiceSegment(
                segment_id="seg_narr",
                episode_id="ep_test",
                seq_index=3,
                segment_kind="NARRATION",
                start_ms=255_000,
                end_ms=260_000,
                audio_path="audio/narr.wav",
                narration_version_sha256=SHA,
            ),
        ]
    )
    assert resolve_case_board_spine_at_ms(voice, scenes) == 255_000


def test_propose_manifest_honest_1200_second_split_and_hero_caps() -> None:
    plans = _full_twenty_minute_plans()
    voice = _voice(
        segments=[
            VoiceSegment(
                segment_id="seg_open",
                episode_id="ep_test",
                seq_index=1,
                segment_kind="NARRATION",
                start_ms=0,
                end_ms=TARGET_DURATION_MS,
                audio_path="audio/master.wav",
                narration_version_sha256=SHA,
            )
        ],
        word_timestamps=[
            WordTimestamp(
                segment_id="seg_open",
                word="recap.",
                start_ms=218_000,
                end_ms=220_000,
            )
        ],
    )
    proposal = propose_manifest(
        manifest_id="manifest_test",
        episode_id="ep_test",
        case_id="case_test",
        cold_open_archetype="911_CALL_IN_MEDIA_RES",
        flow_backend_mode="GEMINI_OMNI_INTERACTIONS",
        scene_plans=plans,
        voice=voice,
    )
    manifest = proposal.production_manifest
    assert manifest.target_duration_ms == TARGET_DURATION_MS
    assert manifest.code_foia_ms == CODE_FOIA_MS
    assert manifest.still_2k_ms == STILL_2K_MS
    assert manifest.hero_ms == HERO_MS
    assert manifest.hero_clip_count == 10
    assert manifest.hero_duration_sec == 80
    assert len(proposal.timeline_specs) == 10
    assert proposal.case_board_spine_at_ms == 220_000


def test_propose_manifest_spine_inside_210_270_with_foia_slot() -> None:
    plans = _full_twenty_minute_plans()
    voice = _voice(
        segments=[
            VoiceSegment(
                segment_id="seg_pre",
                episode_id="ep_test",
                seq_index=1,
                segment_kind="NARRATION",
                start_ms=0,
                end_ms=230_000,
                audio_path="audio/pre.wav",
                narration_version_sha256=SHA,
            ),
            VoiceSegment(
                segment_id="seg_911",
                episode_id="ep_test",
                seq_index=2,
                segment_kind="FOIA_AUDIO_SLOT",
                start_ms=230_000,
                end_ms=255_000,
                foia_asset_id="foia_911",
            ),
            VoiceSegment(
                segment_id="seg_rest",
                episode_id="ep_test",
                seq_index=3,
                segment_kind="NARRATION",
                start_ms=255_000,
                end_ms=TARGET_DURATION_MS,
                audio_path="audio/master.wav",
                narration_version_sha256=SHA,
            ),
        ]
    )
    proposal = propose_manifest(
        manifest_id="manifest_test",
        episode_id="ep_test",
        case_id="case_test",
        cold_open_archetype="911_CALL_IN_MEDIA_RES",
        flow_backend_mode="GEMINI_OMNI_INTERACTIONS",
        scene_plans=plans,
        voice=voice,
    )
    assert proposal.case_board_spine_at_ms == 255_000


def test_first_and_last_frame_over_ten_seconds_rejected() -> None:
    with pytest.raises(ValidationError, match="FIRST_AND_LAST_FRAME duration"):
        _scene_plan(
            scene_plan_id="plan_bad_hero",
            scene_id="scene_bad_hero",
            seq_index=1,
            engine="FLOW_HERO_VIDEO",
            motif="HeroVideoBridge",
            prompt_mode="FIRST_AND_LAST_FRAME",
            start_ms=0,
            end_ms=11_000,
            keyframes=[
                KeyframeRef(ref_id="kf_start", role="START", sha256=SHA),
                KeyframeRef(ref_id="kf_end", role="END", sha256=SHA),
            ],
        )


def test_timeline_sha256_is_stable() -> None:
    plans = _full_twenty_minute_plans()
    voice = _voice(
        segments=[
            VoiceSegment(
                segment_id="seg_voice",
                episode_id="ep_test",
                seq_index=1,
                segment_kind="NARRATION",
                start_ms=0,
                end_ms=TARGET_DURATION_MS,
                audio_path="audio/master.wav",
                narration_version_sha256=SHA,
            )
        ],
        word_timestamps=[
            WordTimestamp(
                segment_id="seg_voice",
                word="stable.",
                start_ms=218_000,
                end_ms=220_000,
            )
        ],
    )
    first = propose_manifest(
        manifest_id="manifest_test",
        episode_id="ep_test",
        case_id="case_test",
        cold_open_archetype="911_CALL_IN_MEDIA_RES",
        flow_backend_mode="GEMINI_OMNI_INTERACTIONS",
        scene_plans=plans,
        voice=voice,
    )
    second = propose_manifest(
        manifest_id="manifest_test",
        episode_id="ep_test",
        case_id="case_test",
        cold_open_archetype="911_CALL_IN_MEDIA_RES",
        flow_backend_mode="GEMINI_OMNI_INTERACTIONS",
        scene_plans=plans,
        voice=voice,
    )
    assert first.production_manifest.timeline_validated_sha256
    assert (
        first.production_manifest.timeline_validated_sha256
        == second.production_manifest.timeline_validated_sha256
    )
    assert len(first.production_manifest.timeline_validated_sha256) == len(hashlib.sha256(b"").hexdigest())