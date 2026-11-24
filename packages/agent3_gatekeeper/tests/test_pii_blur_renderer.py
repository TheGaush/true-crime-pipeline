"""Deterministic visual blur and spoken PII tone-mute scrubber tests.

No network and no real video encoder.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agent3_gatekeeper.pii_blur_renderer import (
    MIN_GAUSSIAN_SIGMA,
    SPOKEN_TONE_DBFS,
    STATUS_BLURRED,
    STATUS_CRISP,
    STATUS_MUTED,
    STATUS_UNMUTED,
    PiiBlurRenderer,
    ScrubState,
    SpokenPiiInterval,
    VisualPiiBox,
    apply_scrub_plan,
    audit_post_scrub,
    media_has_video_track,
    plan_pii_scrub,
    write_scrub_plan_json,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "pii_blur_renderer.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}

REPO_ROOT = Path(__file__).resolve().parents[3]
BODYCAM_FIXTURE = REPO_ROOT / "fixtures" / "synthetic_media" / "bodycam_440hz_music_042profanity.mp4"
WAV_911 = REPO_ROOT / "fixtures" / "synthetic_media" / "911_spoken_pii.wav"
TRANSCRIPT = REPO_ROOT / "fixtures" / "synthetic_media" / "911_spoken_pii.transcript.json"

_FACE_BOX = VisualPiiBox(
    box_id="bystander_face_0",
    x=120,
    y=80,
    width=96,
    height=120,
    start_ms=5_000,
    end_ms=12_000,
)
_PLATE_BOX = VisualPiiBox(
    box_id="license_plate_0",
    x=640,
    y=400,
    width=180,
    height=40,
    start_ms=18_000,
    end_ms=22_000,
)


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_every_visual_box_plans_sigma_at_least_25() -> None:
    plan = plan_pii_scrub(
        [_FACE_BOX, _PLATE_BOX],
        [],
        asset_id="foia_bodycam",
        source_path=BODYCAM_FIXTURE,
    )
    assert plan.has_video_track is True
    assert len(plan.blur_operations) == 2
    for op in plan.blur_operations:
        assert op.sigma >= MIN_GAUSSIAN_SIGMA
        assert op.sigma == MIN_GAUSSIAN_SIGMA


def test_spoken_intervals_plan_negative_24_dbfs_tone() -> None:
    intervals = [
        SpokenPiiInterval(start_ms=900, end_ms=2_100, kind="person_name"),
        SpokenPiiInterval(start_ms=2_400, end_ms=3_600, kind="street"),
        SpokenPiiInterval(start_ms=4_000, end_ms=5_200, kind="phone"),
    ]
    plan = plan_pii_scrub([], intervals, asset_id="foia_911", source_path=WAV_911)
    assert plan.has_video_track is False
    assert len(plan.mute_operations) == 3
    for op in plan.mute_operations:
        assert op.tone_dbfs == SPOKEN_TONE_DBFS


def test_audio_only_wav_has_no_video_track_still_mutes_spoken_pii(tmp_path: Path) -> None:
    intervals = [SpokenPiiInterval(start_ms=1_000, end_ms=2_500)]
    renderer = PiiBlurRenderer()
    plan, state, audit, out_path = renderer.render(
        [],
        intervals,
        asset_id="case_911_audio",
        source_path=WAV_911,
        scrubbed_foia_dir=tmp_path / "scrubbed_foia",
    )
    assert media_has_video_track(WAV_911) is False
    assert plan.has_video_track is False
    assert plan.blur_operations == []
    assert len(plan.mute_operations) == 1
    assert state.interval_status[intervals[0].interval_key] == STATUS_MUTED
    assert audit.passed is True
    assert plan.spoken_pii_bleeped == 1
    assert out_path.suffix == ".json"
    assert "scrubbed_foia" in out_path.parts


def test_post_scrub_audit_fails_on_residual_crisp_or_unmuted() -> None:
    boxes = [_FACE_BOX]
    intervals = [SpokenPiiInterval(start_ms=500, end_ms=1_200)]
    plan = plan_pii_scrub(boxes, intervals, asset_id="x", source_path=BODYCAM_FIXTURE)
    bad_state = ScrubState(
        box_status={_FACE_BOX.box_id: STATUS_CRISP},
        interval_status={intervals[0].interval_key: STATUS_UNMUTED},
    )
    audit = audit_post_scrub(bad_state, boxes, intervals)
    assert audit.passed is False
    assert audit.visual_pii_blurred == 0
    assert audit.spoken_pii_bleeped == 0
    assert _FACE_BOX.box_id in audit.crisp_boxes
    assert intervals[0].interval_key in audit.unmuted_intervals

    good_state = apply_scrub_plan(plan)
    good_audit = audit_post_scrub(good_state, boxes, intervals)
    assert good_audit.passed is True
    assert good_audit.visual_pii_blurred == 1
    assert good_audit.spoken_pii_bleeped == 1


def test_write_scrub_plan_json_not_real_media(tmp_path: Path) -> None:
    spoken = [SpokenPiiInterval(start_ms=0, end_ms=500)]
    plan = plan_pii_scrub(
        [_FACE_BOX],
        spoken,
        asset_id="asset_json_only",
        source_path=BODYCAM_FIXTURE,
    )
    state = apply_scrub_plan(plan)
    audit = audit_post_scrub(state, [_FACE_BOX], spoken)
    plan.visual_pii_blurred = audit.visual_pii_blurred
    plan.spoken_pii_bleeped = audit.spoken_pii_bleeped
    out = write_scrub_plan_json(plan, scrubbed_foia_dir=tmp_path)
    assert out.name == "asset_json_only.scrub_plan.json"
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["asset_id"] == "asset_json_only"
    assert payload["visual_pii_blurred"] == 1
    assert payload["blur_operations"][0]["sigma"] >= MIN_GAUSSIAN_SIGMA
    assert out.stat().st_size < 10_000


def test_façade_end_to_end_bodycam_and_911_transcript(tmp_path: Path) -> None:
    transcript = json.loads(TRANSCRIPT.read_text(encoding="utf-8"))
    assert transcript["asset_role"] == "911_spoken_pii"
    spoken = [
        SpokenPiiInterval(start_ms=800, end_ms=1_600, kind="person_name"),
        SpokenPiiInterval(start_ms=1_900, end_ms=2_900, kind="street"),
        SpokenPiiInterval(start_ms=3_200, end_ms=4_400, kind="phone"),
    ]
    renderer = PiiBlurRenderer()
    plan, _state, audit, out_path = renderer.render(
        [_FACE_BOX, _PLATE_BOX],
        spoken,
        asset_id="golden_foia_combo",
        source_path=BODYCAM_FIXTURE,
        scrubbed_foia_dir=tmp_path,
    )
    assert audit.passed is True
    assert plan.visual_pii_blurred == 1
    assert plan.spoken_pii_bleeped == 1
    assert out_path.exists()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["spoken_pii_bleeped"] == 1
    assert on_disk["has_video_track"] is True


def test_audio_only_rejects_visual_boxes() -> None:
    with pytest.raises(ValueError, match="audio-only"):
        plan_pii_scrub(
            [_FACE_BOX],
            [],
            asset_id="bad",
            source_path=WAV_911,
        )


def test_blur_sigma_below_minimum_rejected() -> None:
    with pytest.raises(ValueError, match="blur_sigma"):
        plan_pii_scrub([], [], asset_id="x", source_path=BODYCAM_FIXTURE, blur_sigma=10)