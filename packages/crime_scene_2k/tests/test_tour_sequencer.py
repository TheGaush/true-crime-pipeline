"""A 50 second tour keeps an exact frame count and a bounded zoom."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "tour_sequencer.py"
_SPEC = importlib.util.spec_from_file_location("tc_task148_tour", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_tour = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _tour
_SPEC.loader.exec_module(_tour)


def test_four_anchor_tour_is_1500_frames_and_opposite_corners_dip():
    anchors = [
        _tour.Anchor(128, 72, 2.6),
        _tour.Anchor(2430, 1360, 2.8),
        _tour.Anchor(400, 200, 2.2),
        _tour.Anchor(1800, 900, 2.4),
    ]
    plan = _tour.plan_tour(50.0, anchors)
    assert plan.nb_frames == 1500
    assert plan.peak_zoom <= 3.8
    mid = min(plan.frames, key=lambda frame: frame.zoom)
    assert mid.zoom < 1.2


def test_empty_tour_pushes_and_an_early_cue_shortens_travel():
    empty = _tour.plan_tour(4.0, [])
    assert empty.nb_frames == 120
    assert abs(empty.frames[0].zoom - 1.0) < 1e-6
    assert abs(empty.frames[-1].zoom - 1.18) < 1e-6
    early = _tour.plan_tour(10.0, [_tour.Anchor(200, 200, 2.0), _tour.Anchor(1800, 900, 2.4)], cue_sec=0.3)
    assert early.nb_frames == 300
    assert early.peak_zoom <= 3.8
