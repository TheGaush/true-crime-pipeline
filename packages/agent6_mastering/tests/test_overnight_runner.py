import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "overnight_runner.py"
_SPEC = importlib.util.spec_from_file_location("tc174_night", _PATH)
assert _SPEC and _SPEC.loader
night = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = night
_SPEC.loader.exec_module(night)


def test_resume_and_missing_hero_fallback(tmp_path: Path):
    manifest = {
        "episode_id": "ep_golden_01",
        "scenes": [
            {"scene_id": "draw", "visual_engine": "CODE_STICKMAN"},
            {"scene_id": "still", "visual_engine": "STILL_2K_PANZOOM"},
            {"scene_id": "hero", "visual_engine": "FLOW_HERO_VIDEO", "fallback_engine": "STILL_2K_PANZOOM"},
            {"scene_id": "body", "visual_engine": "FOIA_REAL_FOOTAGE"},
        ],
    }
    try:
        night.run(str(tmp_path), manifest, kill_after="STAGE_MUX")
        assert False
    except night.OvernightStop:
        pass
    state = night._load(tmp_path)
    assert state["status"] == "INTERRUPTED"
    assert state["completed"] == ["STAGE_INGEST", "STAGE_AUDIO", "STAGE_VIDEO_GRADE"]
    finished = night.run(str(tmp_path), manifest)
    assert finished["completed"] == list(night.STAGES)
    assert finished["note"]["missing"][0]["scene_id"] == "hero"
    assert (tmp_path / "ready_to_upload" / "ep_golden_01" / "qa_certificate.json").is_file()
