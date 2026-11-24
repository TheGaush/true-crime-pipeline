import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "crime_scene_2k" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "agent6_mastering" / "src"))
call = importlib.import_module("crime_scene_2k.callout_projector")
audio = importlib.import_module("agent6_mastering.audio_timeline")


def test_edge_callouts_and_lcut_agree():
    for args in ((128, 72, 0, 0, 800, 450), (2432, 1368, 1760, 990, 800, 450)):
        point = call.project(*args)
        found = call.ring_centroid(call.render_ring(point))
        error = ((found[0] - point.x) ** 2 + (found[1] - point.y) ** 2) ** 0.5
        assert error <= 1.0
    plan = audio.schedule(
        [
            {"scene_id": "narr", "duration_ms": 4000, "visual_engine": "CODE_STICKMAN"},
            {"scene_id": "foia", "duration_ms": 4000, "visual_engine": "FOIA_REAL_FOOTAGE"},
        ],
        l_cut_ms=800,
    )
    assert plan.total_master_timeline_ms == 8000
    assert plan.track2[0]["start_ms"] == 4000 - 800
    assert abs((plan.track2[0]["end_ms"] - plan.track2[0]["start_ms"]) - (4000 + 800)) <= 1
