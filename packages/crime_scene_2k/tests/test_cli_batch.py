"""Batch and single-scene 2K renders."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "cli.py"
_SPEC = importlib.util.spec_from_file_location("tc150_cli", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _cli
_SPEC.loader.exec_module(_cli)


def test_batch_and_single_scene(tmp_path: Path):
    stills = tmp_path / "stills"
    stills.mkdir()
    Image.new("RGB", (2560, 1440), (233, 226, 210)).save(stills / "room.png")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "scenes": [
                    {"scene_id": "wide", "visual_engine": "STILL_2K_PANZOOM", "still_asset_id": "room", "duration_sec": 0.4},
                    {"scene_id": "desk", "visual_engine": "STILL_2K_PANZOOM", "still_asset_id": "room", "duration_sec": 0.4},
                    {"scene_id": "hero", "visual_engine": "FLOW_HERO_VIDEO"},
                ]
            }
        ),
        encoding="utf8",
    )
    report = _cli.render_manifest(str(manifest), str(stills), str(tmp_path / "out"))
    assert [row["scene_id"] for row in report["scenes"]] == ["wide", "desk"]
    assert all(_cli.probe_ok(row["mp4"]) for row in report["scenes"])
    one = _cli.render_manifest(str(manifest), str(stills), str(tmp_path / "one"), "desk")
    assert [row["scene_id"] for row in one["scenes"]] == ["desk"]
    assert _cli.main(["render", "--manifest", str(manifest), "--stills-dir", str(stills), "--out-dir", str(tmp_path / "cli"), "--scene", "missing"]) == 2
