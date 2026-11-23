"""End-to-end motion asset report for a tiny golden-shaped manifest."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "python_motion" / "service.py"
_SPEC = importlib.util.spec_from_file_location("tc141_service", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_service = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _service
_SPEC.loader.exec_module(_service)


def test_report_covers_bookends_and_sfx_with_posix_paths(tmp_path: Path):
    manifest = tmp_path / "ep_golden_01.json"
    manifest.write_text(
        json.dumps(
            {
                "episode_id": "ep_golden_01",
                "scenes": [
                    {"scene_id": "hero_1", "visual_engine": "FLOW_HERO_VIDEO", "prompt_mode": "TEXT_TO_VIDEO", "duration_sec": 0.4, "waypoints": [[100, 200], [400, 300]]},
                    {"scene_id": "map_1", "visual_engine": "CODE_STICKMAN", "duration_sec": 0.4},
                ],
                "sfx_cues": [{"cue_type": "typewriter_key", "duration_ms": 30}],
            }
        ),
        encoding="utf8",
    )
    report = _service.build_assets(_service.BuildRequest(str(manifest), str(tmp_path / "out")))
    assert report["ok"] is True
    assert report["bookends"][0]["start_frame"] is None
    assert report["bookends"][0]["safety_passed"] is True
    assert report["sfx"][0]["sample_rate_hz"] == 48000
    assert report["trajectories"][0]["nb_frames"] == 12
    assert "\\" not in json.dumps(report)
    only = _service.build_assets(_service.BuildRequest(str(manifest), str(tmp_path / "sfx-only"), only_sfx=True))
    assert only["bookends"] == []
    assert len(only["sfx"]) == 1
    assert _service.main(["build", "--manifest", str(manifest), "--out-dir", str(tmp_path / "cli"), "--only-bookends"]) == 0
    animated = _service.build_assets(_service.BuildRequest(str(manifest), str(tmp_path / "anim"), animatic=True))
    assert animated["animatic"]["total_duration_sec"] == 0.8
