import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared_contracts" / "src"))
from shared_contracts.models import ReadyToUploadPack, ScenePlan, VoiceTrackManifest

SHA = "a" * 64


def test_empty_cues_and_ready_pack_roundtrip():
    scene = ScenePlan(
        scene_plan_id="plan_1",
        episode_id="ep_golden_01",
        scene_id="scene_1",
        seq_index=1,
        story_purpose="Open the file",
        intended_audience_effect="Orient the viewer",
        approved_narration_text="The folder was already on the desk.",
        narration_version_sha256=SHA,
        cited_fact_ids_json=["fact_1"],
        visual_concept="A desk at night",
        visual_engine="CODE_STICKMAN",
        motif_component="StickmanStage",
        prompt_mode="TEXT_TO_VIDEO",
        visual_prompt="A quiet desk, no people.",
        expected_output_summary="Desk plate",
        timing_start_ms=0,
        timing_end_ms=4000,
        transition_spec_json={"transition_type": "CUT", "duration_ms": 0},
        sound_cues_json=[],
        edit_instructions="Hold the wide shot.",
        acceptance_criteria_json=[{"criterion_id": "c1", "kind": "SEMANTIC", "text": "The desk reads clearly."}],
        created_at=1,
        updated_at=1,
    )
    voice = VoiceTrackManifest(
        episode_id="ep_golden_01",
        total_master_ms=4000,
        segments=[
            {
                "segment_id": "seg_1",
                "episode_id": "ep_golden_01",
                "seq_index": 1,
                "segment_kind": "NARRATION",
                "start_ms": 0,
                "end_ms": 4000,
                "audio_path": "voice/seg_1.wav",
                "narration_version_sha256": SHA,
            }
        ],
        cue_points=[],
    )
    ready = ReadyToUploadPack(
        episode_id="ep_golden_01",
        episode_slug="ep_golden_01",
        ready_pack_dir="ready/ep_golden_01",
        ready_bundle_sha256=SHA,
        final_mp4_relpath="final_1080p30.mp4",
        final_mp4_sha256=SHA,
        integrated_lufs=-14.0,
        true_peak_dbtp=-1.2,
        lufs_passed=True,
        safe_zone_passed=True,
        vision_frame_qa_status="PASSED",
        thumbnail_brand_passed=True,
        thumbnail_relpaths=["thumbnails/variant_a.png"],
        chapters_relpath="chapters.txt",
        youtube_synthetic_disclosure_required=True,
        provenance_bundle_relpath="provenance_bundle.json",
        qa_certificate_relpath="qa_certificate.json",
        approved_release_gates=[
            "FACTUAL_ACCURACY",
            "PRIVACY_PII",
            "SOURCE_RIGHTS",
            "SYNTHETIC_DISCLOSURE",
            "ILLUSTRATIVE_LABELING",
        ],
    )
    assert scene.sound_cues_json == []
    assert voice.cue_points == []
    assert ready.integrated_lufs == -14.0
    assert ScenePlan.model_validate(scene.model_dump()).scene_id == "scene_1"
