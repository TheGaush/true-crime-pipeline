"""Spline, zero-length, and 30 fps checks for the trajectory engine."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

_PATH = Path(__file__).resolve().parents[1] / "src" / "python_motion" / "trajectory_engine.py"
_SPEC = importlib.util.spec_from_file_location("tc_task136_trajectory", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_traj = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _traj
_SPEC.loader.exec_module(_traj)


def test_spline_easing_and_bearing():
    points = [(100.0, 200.0), (400.0, 220.0), (700.0, 500.0), (900.0, 300.0)]
    start = _traj.catmull_rom(points, 0.0)
    end = _traj.catmull_rom(points, 1.0)
    mid = _traj.catmull_rom(points, 0.5)
    assert start == (100.0, 200.0)
    assert abs(end[0] - 900.0) < 1.0
    assert abs(end[1] - 300.0) < 1.0
    assert mid != start
    assert _traj.ease_in_out_cubic(0.0) == 0.0
    assert _traj.ease_in_out_cubic(1.0) == 1.0
    assert _traj.bearing_deg((0.0, 0.0), (0.0, -10.0)) == 0.0


def test_zero_length_and_long_polylines_do_not_crash():
    still = _traj.catmull_rom([(40.0, 40.0), (40.0, 40.0)], 0.7)
    assert still == (40.0, 40.0)
    dense = [(float(index), 10.0) for index in range(240)]
    simplified = _traj.rdp(dense, 1.5)
    assert len(simplified) < 10
    assert _traj.catmull_rom(dense, 1.0)[0] == 239.0


def test_frame_clock_and_flow_palette(tmp_path: Path):
    assert _traj.frame_count(7.33) == 220
    assert _traj.progress_at(219, 220) == 1.0
    request = _traj.TrajectoryRequest(
        waypoints=((200.0, 400.0), (900.0, 500.0), (1400.0, 700.0)),
        duration_sec=0.5,
        out_path=str(tmp_path / "route.mp4"),
        for_flow_keyframe=True,
    )
    result = _traj.TrajectoryRenderer().render_mp4(request)
    assert result["nb_frames"] == 15
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,nb_frames,width,height", "-of", "json", request.out_path],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probe.stdout)["streams"][0]
    assert stream["r_frame_rate"] == "30/1"
    assert stream["nb_frames"] == "15"
    assert stream["width"] == 1920
    frame = np.asarray(_traj.TrajectoryRenderer().render_frame(request, 0))
    red = frame[..., 0].astype(np.int16)
    green = frame[..., 1].astype(np.int16)
    blue = frame[..., 2].astype(np.int16)
    assert int(np.count_nonzero((red > 160) & (red > green * 1.8) & (red > blue * 1.8))) == 0
