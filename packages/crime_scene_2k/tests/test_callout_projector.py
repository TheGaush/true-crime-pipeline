"""Screen-space callouts stay on the anchor, including clamped corners."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "callout_projector.py"
_SPEC = importlib.util.spec_from_file_location("tc_task146_callout", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_call = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _call
_SPEC.loader.exec_module(_call)


def test_center_is_the_screen_center_and_corners_are_not():
    center = _call.project(1280, 720, 640, 360, 1280, 720)
    assert abs(center.x - 960) <= 0.5
    assert abs(center.y - 540) <= 0.5
    corner = _call.project(128, 72, 0, 0, 800, 450)
    assert abs(corner.x - 307.2) < 1.0
    assert abs(corner.y - 172.8) < 1.0
    back = _call.unproject(corner, 0, 0, 800, 450)
    assert abs(back[0] - 128) < 1.0
    assert abs(back[1] - 72) < 1.0


def test_rendered_centroid_and_label_margin():
    point = _call.project(128, 72, 0, 0, 800, 450)
    centroid = _call.ring_centroid(_call.render_ring(point))
    assert abs(centroid[0] - point.x) < 1.0
    assert abs(centroid[1] - point.y) < 1.0
    label = _call.place_label(point)
    assert label.x >= _call.SAFE_X
    assert label.y >= _call.SAFE_Y
    assert label.x + label.width <= 1920 - _call.SAFE_X
    assert label.y + label.height <= 1080 - _call.SAFE_Y
