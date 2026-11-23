"""Lanczos pans stay sub-pixel and the MP4 is 30 fps."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "lanczos_renderer.py"
_SPEC = importlib.util.spec_from_file_location("tc_task147_lanczos", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_lanczos = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _lanczos
_SPEC.loader.exec_module(_lanczos)


def _plate() -> np.ndarray:
    height, width = 1440, 2560
    y, x = np.mgrid[0:height, 0:width]
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[..., 0] = (x / 10).astype(np.uint8)
    image[..., 1] = (y / 6).astype(np.uint8)
    image[..., 2] = 180
    return image


def test_fractional_pan_changes_the_plate_and_the_clip_is_cfr(tmp_path: Path):
    image = _plate()
    start = _lanczos.CameraWaypoint(1280, 720, 1.8)
    nudged = _lanczos.sample_camera(start, _lanczos.CameraWaypoint(1280.4, 720, 1.8), 1.0)
    first = _lanczos.warp_frame(image, start)
    second = _lanczos.warp_frame(image, nudged)
    assert first.shape == (1080, 1920, 3)
    assert not np.array_equal(first, second)
    flat = np.full_like(image, (210, 226, 233))
    graded = _lanczos.warp_frame(flat, start)
    assert float(graded[:40, :40, 0].std()) < 2.0
    path = tmp_path / "pan.mp4"
    frames = _lanczos.render_mp4(image, start, _lanczos.CameraWaypoint(1500, 800, 2.2), 0.5, str(path))
    assert frames == 15
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,nb_frames,width,height", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["r_frame_rate"] == "30/1"
    assert stream["nb_frames"] == "15"
    assert stream["width"] == 1920
    assert stream["height"] == 1080
