"""480p animatic duration, slate text, and a 1,200 second timing check."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import time
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "python_motion" / "animatic_builder.py"
_SPEC = importlib.util.spec_from_file_location("tc_task138_animatic", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_anim = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _anim
_SPEC.loader.exec_module(_anim)


def test_cards_carry_ids_and_a_missing_foia_stub():
    card = _anim.render_card({"scene_id": "scene_foia", "visual_engine": "FOIA_REAL_FOOTAGE", "word_count": 12}, True)
    assert card.size == (854, 480)
    assert card.getpixel((50, 320)) == (0x1B, 0x1B, 0x1D)


def test_short_manifest_matches_duration_and_telemetry(tmp_path: Path):
    manifest = {
        "episode_id": "ep_short",
        "scenes": [
            {"scene_id": "a", "visual_engine": "CODE_STICKMAN", "duration_ms": 1000, "word_count": 4},
            {"scene_id": "b", "visual_engine": "CODE_STICKMAN", "duration_ms": 2000, "word_count": 8},
            {"scene_id": "c", "visual_engine": "FLOW_HERO_VIDEO", "duration_ms": 1000, "word_count": 3},
            {"scene_id": "d", "visual_engine": "STILL_2K_PANZOOM", "duration_ms": 1000, "word_count": 2},
        ],
    }
    result = _anim.build_animatic(manifest, str(tmp_path))
    probe = _probe(result.mp4_path)
    assert probe["r_frame_rate"] == "30/1"
    assert abs(float(probe["duration"]) - 5.0) <= 0.1
    assert result.hero_clip_count == 1
    assert result.max_code_streak_sec == 3.0
    body = json.loads(Path(result.telemetry_path).read_text(encoding="utf8"))
    assert body["remote_calls"] == 0


def test_twenty_minute_animatic_finishes_quickly(tmp_path: Path):
    manifest = {
        "episode_id": "ep_golden_01",
        "scenes": [
            {"scene_id": f"s{index:03d}", "visual_engine": "CODE_STICKMAN" if index % 5 else "FLOW_HERO_VIDEO", "duration_ms": 12000, "word_count": 20}
            for index in range(100)
        ],
    }
    started = time.perf_counter()
    result = _anim.build_animatic(manifest, str(tmp_path))
    elapsed = time.perf_counter() - started
    assert elapsed < 25.0
    assert result.total_duration_sec == 1200.0
    probe = _probe(result.mp4_path)
    assert probe["r_frame_rate"] == "30/1"
    assert abs(float(probe["duration"]) - 1200.0) <= 0.1


def _probe(path: str) -> dict[str, str]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=r_frame_rate", "-of", "json", path],
        check=True,
        capture_output=True,
        text=True,
    )
    body = json.loads(result.stdout)
    return {"duration": body["format"]["duration"], "r_frame_rate": body["streams"][0]["r_frame_rate"]}
