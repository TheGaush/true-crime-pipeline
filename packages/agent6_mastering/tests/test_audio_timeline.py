import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "audio_timeline.py"
_SPEC = importlib.util.spec_from_file_location("tc164_audio", _PATH)
assert _SPEC and _SPEC.loader
audio = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = audio
_SPEC.loader.exec_module(audio)


def test_lcut_clamps_and_the_timeline_locks():
    scenes = [
        {"scene_id": "open", "visual_engine": "FOIA_REAL_FOOTAGE", "duration_ms": 4000},
        {"scene_id": "narrate", "visual_engine": "CODE_STICKMAN", "duration_ms": 8000},
        {"scene_id": "call", "visual_engine": "AUDIO_EVIDENCE_CARD", "duration_ms": 5000},
    ]
    plan = audio.schedule(scenes, [{"cue_id": "key", "start_ms": 1200}], l_cut_ms=800)
    assert plan.total_master_timeline_ms == 17_000
    assert plan.track2[0]["start_ms"] == 0
    assert plan.track2[1]["start_ms"] == 12_000 - 800
    assert plan.track1[0]["gain"] == 1.0
    assert plan.track3["end_ms"] == 17_000
    assert plan.track4[0]["sample_rate_hz"] == 48000
    assert all(row["mute_track1"] for row in plan.track2)
