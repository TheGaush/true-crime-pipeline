import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "flow_adapter" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "analytics_feedback" / "src"))
sys.path.insert(0, str(ROOT / "packages" / "agent6_mastering" / "src"))
desk = importlib.import_module("flow_adapter.batch_desk_backend")
cal = importlib.import_module("analytics_feedback.calibrator")
night = importlib.import_module("agent6_mastering.overnight_runner")


def test_lock_heal_note_and_atomic_weights(tmp_path: Path):
    account = desk.Account("tab-1")
    desk.reserve_credit(account, 0)
    try:
        desk.checkout(account, desk.DAILY_LOCK_MS - 1)
        assert False
    except desk.AccountLockedError:
        pass
    other = desk.Account("tab-2")
    assert desk.checkout(other, 10) == "tab-2"
    report = cal.calibrate(
        [
            {"adsense_status": "yellow_icon", "tags": ["cold-case"], "retention_min6_14_pct": 40, "thumbnail_archetype": "doorway_silhouette", "ctr_pct": 3.0},
            {"adsense_status": "yellow_icon", "tags": ["cold-case"], "retention_min6_14_pct": 42, "thumbnail_archetype": "doorway_silhouette", "ctr_pct": 3.2},
            {"adsense_status": "UNKNOWN", "tags": ["court"], "retention_min6_14_pct": 38, "thumbnail_archetype": "desk_evidence_closeup", "ctr_pct": 8.0},
        ]
    )
    assert "cold-case" in report["yellow_tags"]
    assert -0.15 <= report["adjustment"] <= 0.15
    target = tmp_path / "calibration_weights.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report), encoding="utf8")
    temporary.replace(target)
    assert json.loads(target.read_text(encoding="utf8"))["yellow_tags"] == ["cold-case"]
    manifest = {"episode_id": "ep_slice", "scenes": [{"scene_id": "hero", "visual_engine": "FLOW_HERO_VIDEO", "duration_ms": 4000}]}
    try:
        night.run(str(tmp_path / "ep"), manifest, kill_after="STAGE_MUX")
        assert False
    except night.OvernightStop:
        pass
    finished = night.run(str(tmp_path / "ep"), manifest)
    assert finished["note"]["missing"][0]["scene_id"] == "hero"
    assert (tmp_path / "ep" / "ready_to_upload" / "ep_slice" / "qa_certificate.json").is_file()
