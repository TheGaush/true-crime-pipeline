"""Pixel and pose checks for the monochrome stickman keyframe renderer."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "python_motion" / "stickman_pil.py"
_SPEC = importlib.util.spec_from_file_location("tc_task133_stickman_pil", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_stick = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _stick
_SPEC.loader.exec_module(_stick)

INK = np.array(_stick.INK, dtype=np.int16)
PARCHMENT = np.array(_stick.PARCHMENT, dtype=np.int16)
CRIMSON = (201, 42, 42)


def renderer():
    return _stick.StickmanRenderer()


def request(**kwargs):
    return _stick.StickmanRenderRequest(**kwargs)


def rgb(frame) -> np.ndarray:
    return np.asarray(frame.image.convert("RGB"))


def test_eight_poses_are_deterministic_and_free_of_red_triggers():
    engine = renderer()
    hashes: dict[str, str] = {}
    for pose in _stick.POSE_IDS:
        phase = 0.25 if pose == "walking" else 0.0
        first = engine.render(request(pose=pose, walk_phase=phase))
        second = engine.render(request(pose=pose, walk_phase=phase, seed=4))
        assert first.sha256 == second.sha256
        assert first.mode == "RGB"
        assert first.image.size == (1280, 720)
        assert rgb(first).dtype == np.uint8
        assert rgb(first).shape == (720, 1280, 3)
        assert _stick.red_trigger_count(rgb(first)) == 0
        assert first.stroke_px == 6
        assert first.supersample_size == (2560, 1440)
        hashes[pose] = first.sha256
    assert len(hashes) == 8
    assert len(set(hashes.values())) == 8


def test_pose_angles_match_the_catalog_rig():
    engine = renderer()
    idle = engine.render(request(pose="idle")).sockets
    pointing = engine.render(request(pose="pointing")).sockets
    seated = engine.render(request(pose="seated")).sockets
    walking = engine.render(request(pose="walking", walk_phase=0.25)).sockets
    doorway = engine.render(request(pose="doorway_entry")).sockets
    crossed = engine.render(request(pose="arms_crossed")).sockets
    held = engine.render(request(pose="evidence_hold")).sockets

    assert idle.hand_right[1] > idle.elbow_right[1] + 10
    assert pointing.hand_right[0] > pointing.elbow_right[0] + 20
    assert abs(pointing.hand_right[1] - pointing.elbow_right[1]) < abs(idle.hand_right[1] - idle.elbow_right[1])
    assert abs(seated.knee_left[1] - seated.hip[1]) < abs(idle.knee_left[1] - idle.hip[1])
    assert seated.ankle_left[1] > seated.knee_left[1]
    assert abs(walking.ankle_left[0] - walking.ankle_right[0]) > abs(idle.ankle_left[0] - idle.ankle_right[0]) + 8
    assert abs(doorway.neck[0] - doorway.hip[0]) > abs(idle.neck[0] - idle.hip[0]) + 4
    assert abs(crossed.hand_left[1] - crossed.hand_right[1]) < 30
    assert held.hand_left[1] < idle.hand_left[1] - 20
    assert held.hand_right[1] < idle.hand_right[1] - 20


def test_facing_left_mirrors_about_the_pelvis():
    engine = renderer()
    right = engine.render(request(pose="pointing", facing="right")).sockets
    left = engine.render(request(pose="pointing", facing="left")).sockets
    assert right.hand_right[0] - right.hip[0] == pytest.approx(-(left.hand_right[0] - left.hip[0]), abs=1.5)
    assert right.hand_right[1] == pytest.approx(left.hand_right[1], abs=1.5)


def test_1080p_plate_uses_the_nine_pixel_stroke_and_matches_twice():
    engine = renderer()
    frame = engine.render(request(pose="idle", width=1920, height=1080))
    again = engine.render(request(pose="idle", width=1920, height=1080))
    assert frame.image.size == (1920, 1080)
    assert frame.stroke_px == 9
    assert frame.supersample_size == (3840, 2160)
    assert frame.sha256 == again.sha256
    assert _stick.red_trigger_count(rgb(frame)) == 0
    assert _stick.ssim_luma(rgb(frame), rgb(again)) == pytest.approx(1.0, abs=1e-6)


def test_rgba_is_opaque_and_matches_the_rgb_plate():
    engine = renderer()
    color = engine.render(request(pose="idle", mode="RGB"))
    alpha = engine.render(request(pose="idle", mode="RGBA"))
    assert alpha.mode == "RGBA"
    pixels = np.asarray(alpha.image)
    assert pixels.shape == (720, 1280, 4)
    assert int(pixels[..., 3].min()) == 255
    assert np.array_equal(pixels[..., :3], rgb(color))


def test_charcoal_background_keeps_a_parchment_figure():
    frame = renderer().render(request(pose="detective_silhouette", background="charcoal"))
    pixels = rgb(frame)
    assert tuple(int(v) for v in pixels[0, 0]) == _stick.INK
    parchment = np.all(pixels == np.array(_stick.PARCHMENT, dtype=np.uint8), axis=2)
    assert int(parchment.sum()) > 200
    assert _stick.red_trigger_count(pixels) == 0


def test_detective_silhouette_covers_more_ink_than_the_idle_stroke():
    engine = renderer()
    idle = rgb(engine.render(request(pose="idle")))
    detective = rgb(engine.render(request(pose="detective_silhouette")))
    ink = np.array(_stick.INK, dtype=np.uint8)
    idle_ink = int(np.all(idle == ink, axis=2).sum())
    detective_ink = int(np.all(detective == ink, axis=2).sum())
    assert detective_ink > idle_ink


def test_torso_core_stays_at_least_four_pixels_after_lanczos():
    frame = rgb(renderer().render(request(pose="idle")))
    row = frame[int(frame.shape[0] * 0.62)]
    dark = np.all(row.astype(np.int16) < 80, axis=1)
    runs = _runs(dark)
    assert max(runs, default=0) >= 4


def test_crimson_props_are_remapped_for_flow_and_kept_when_the_guard_is_off(caplog):
    engine = renderer()
    props = ({"kind": "arrow", "color_hex": "#C92A2A"},)
    with caplog.at_level(logging.WARNING, logger="python_motion.stickman"):
        clean = engine.render(request(pose="idle", keyframe_props=props))
    assert _stick.red_trigger_count(rgb(clean)) == 0
    assert any(item["code"] == "CRIMSON_REMAPPED" and item["to"] == "#3A4F66" for item in clean.warnings)
    assert any(json.loads(rec.message)["code"] == "CRIMSON_REMAPPED" for rec in caplog.records)
    stained = engine.render(request(pose="idle", keyframe_props=props, for_flow_keyframe=False))
    assert _stick.red_trigger_count(rgb(stained)) > 35


def test_captions_are_stripped_and_absent_from_the_png():
    frame = renderer().render(
        request(pose="idle", keyframe_props=({"kind": "timestamp", "color_hex": "#1B1B1D", "text": "10:41 PM"},))
    )
    assert any(item["code"] == "TEXT_STRIPPED" for item in frame.warnings)
    assert b"10:41" not in frame.png_bytes
    assert frame.image.info.get("comment") is None
    assert _stick.red_trigger_count(rgb(frame)) == 0


def test_identical_poses_score_perfect_ssim_and_a_stride_does_not():
    engine = renderer()
    idle = rgb(engine.render(request(pose="idle")))
    copy = rgb(engine.render(request(pose="idle")))
    stride = rgb(engine.render(request(pose="walking", walk_phase=0.25)))
    assert _stick.ssim_luma(idle, copy) == pytest.approx(1.0, abs=1e-6)
    assert _stick.ssim_luma(idle, stride) < 0.999


def test_amber_is_not_a_red_trigger_and_crimson_is():
    amber = np.empty((32, 32, 3), dtype=np.uint8)
    amber[:] = _stick.AMBER
    blood = np.empty((32, 32, 3), dtype=np.uint8)
    blood[:] = CRIMSON
    assert _stick.red_trigger_count(amber) == 0
    assert _stick.red_trigger_count(blood) == 32 * 32


def test_unknown_pose_and_odd_sizes_fail_before_a_plate_is_drawn():
    engine = renderer()
    with pytest.raises(_stick.StickmanRenderError) as unknown:
        engine.render(request(pose="running"))
    assert unknown.value.code == "POSE"
    with pytest.raises(_stick.StickmanRenderError) as size:
        engine.render(request(pose="idle", width=640, height=360))
    assert size.value.code == "SIZE"


def _runs(mask: np.ndarray) -> list[int]:
    runs: list[int] = []
    current = 0
    for value in mask.tolist():
        if value:
            current += 1
        elif current:
            runs.append(current)
            current = 0
    if current:
        runs.append(current)
    return runs
