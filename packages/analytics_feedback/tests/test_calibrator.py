import importlib.util
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "analytics_feedback" / "calibrator.py"
_SPEC = importlib.util.spec_from_file_location("tc185_cal", _PATH)
assert _SPEC and _SPEC.loader
cal = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cal
_SPEC.loader.exec_module(cal)


def test_weights_stay_inside_fifteen_percent():
    cold = cal.calibrate([{"adsense_status": "UNKNOWN"}])
    assert cold["confidence"] == "insufficient_sample"
    assert cold["adjustment"] == 0.0
    rows = [
        {"adsense_status": "yellow_icon", "tags": ["cold-case"], "retention_min6_14_pct": 40, "thumbnail_archetype": "doorway_silhouette", "ctr_pct": 3.0},
        {"adsense_status": "yellow_icon", "tags": ["cold-case"], "retention_min6_14_pct": 42, "thumbnail_archetype": "doorway_silhouette", "ctr_pct": 3.2},
        {"adsense_status": "UNKNOWN", "tags": ["court"], "retention_min6_14_pct": 38, "thumbnail_archetype": "desk_evidence_closeup", "ctr_pct": 8.0},
        {"adsense_status": "UNKNOWN", "tags": ["court"], "retention_min6_14_pct": 41, "thumbnail_archetype": "desk_evidence_closeup", "ctr_pct": 7.5},
        {"adsense_status": "UNKNOWN", "tags": ["court"], "retention_min6_14_pct": 72, "thumbnail_archetype": "map_trajectory_split", "ctr_pct": 5.0},
        {"adsense_status": "UNKNOWN", "tags": ["court"], "retention_min6_14_pct": 80, "thumbnail_archetype": "map_trajectory_split", "ctr_pct": 4.0},
    ]
    report = cal.calibrate(rows)
    assert "cold-case" in report["yellow_tags"]
    assert report["midroll"] == "tighten_pattern_interrupt"
    assert report["thumbnails"][0] == "desk_evidence_closeup"
    assert -0.15 <= report["adjustment"] <= 0.15
