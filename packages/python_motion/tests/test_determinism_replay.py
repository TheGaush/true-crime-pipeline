"""Two cold builds of the same manifest must hash the same."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

from python_motion.service import BuildRequest, build_assets


def test_two_cold_builds_match(tmp_path: Path):
    manifest = tmp_path / "manifest.json"
    scenes = [
        {"scene_id": f"hero_{index}", "visual_engine": "FLOW_HERO_VIDEO", "prompt_mode": "TEXT_TO_VIDEO", "duration_sec": 4}
        for index in range(4)
    ]
    cues = [{"cue_type": "paper_slide", "duration_ms": 20} for _ in range(12)]
    manifest.write_text(json.dumps({"episode_id": "ep_replay", "scenes": scenes, "sfx_cues": cues}), encoding="utf8")
    started = time.perf_counter()
    first = build_assets(BuildRequest(str(manifest), str(tmp_path / "a")))
    second = build_assets(BuildRequest(str(manifest), str(tmp_path / "b")))
    assert time.perf_counter() - started < 15
    assert _media(first) == _media(second)
    assert len(first["sfx"]) == 12
    assert all(row["safety_passed"] for row in first["bookends"])


def _media(report: dict) -> str:
    rows = [
        *[row["sha256"] for row in report["sfx"]],
        *[row["start_sha256"] for row in report["bookends"]],
        *[row["end_sha256"] for row in report["bookends"]],
    ]
    return hashlib.sha256(json.dumps(rows).encode("utf8")).hexdigest()
