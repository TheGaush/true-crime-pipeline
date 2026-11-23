"""Bookend pair tests for hero prompt modes and the safety gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

_PATH = Path(__file__).resolve().parents[1] / "src" / "python_motion" / "bookend_generator.py"
_SPEC = importlib.util.spec_from_file_location("tc_task135_bookend", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_book = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _book
_SPEC.loader.exec_module(_book)


def test_text_to_video_writes_no_plates(tmp_path: Path):
    pair = _book.BookendGenerator().generate(
        _book.BookendRequest("scene_t2v", "TEXT_TO_VIDEO", 8.0, str(tmp_path))
    )
    assert pair.start_frame is None
    assert pair.end_frame is None
    assert pair.safety_passed is True
    assert list(tmp_path.glob("*.png")) == []
    meta = json.loads(Path(pair.meta_path).read_text(encoding="utf8"))
    assert meta["prompt_mode"] == "TEXT_TO_VIDEO"
    assert meta["start_sha256"] is None


def test_first_frame_and_pair_pass_safety_and_keep_continuity(tmp_path: Path):
    engine = _book.BookendGenerator()
    first = engine.generate(
        _book.BookendRequest("scene_one", "FIRST_FRAME", 6.0, str(tmp_path), actor_x=0.4)
    )
    pair = engine.generate(
        _book.BookendRequest(
            "scene_two",
            "FIRST_AND_LAST_FRAME",
            8.0,
            str(tmp_path),
            actor_x=0.35,
            end_actor_x=0.55,
            pose="idle",
            end_pose="walking",
            end_walk_phase=0.3,
        )
    )
    assert first.end_frame is None
    assert Image.open(first.start_frame).size == (1280, 720)
    assert pair.start_sha256 != pair.end_sha256
    assert pair.safety_passed is True
    meta = json.loads(Path(pair.meta_path).read_text(encoding="utf8"))
    assert meta["safety_passed"] is True
    assert meta["translation_clamped"] is False
    start = Image.open(pair.start_frame)
    end = Image.open(pair.end_frame)
    assert start.size == end.size == (1280, 720)


def test_large_jump_is_clamped_and_static_beats_gain_parallax(tmp_path: Path):
    engine = _book.BookendGenerator()
    jumped = engine.generate(
        _book.BookendRequest(
            "scene_jump",
            "FIRST_AND_LAST_FRAME",
            4.0,
            str(tmp_path),
            actor_x=0.1,
            end_actor_x=0.95,
            pose="pointing",
            end_pose="pointing",
            end_walk_phase=0.4,
        )
    )
    assert any(item["code"] == "TRANSLATION_CLAMP" for item in jumped.warnings)
    static = engine.generate(
        _book.BookendRequest("scene_static", "FIRST_AND_LAST_FRAME", 5.0, str(tmp_path / "b"))
    )
    meta = json.loads(Path(static.meta_path).read_text(encoding="utf8"))
    assert meta["parallax_applied"] is True
    assert static.start_sha256 != static.end_sha256


def test_duration_and_size_bounds(tmp_path: Path):
    short = _book.BookendGenerator().generate(
        _book.BookendRequest("scene_short", "FIRST_AND_LAST_FRAME", 1.0, str(tmp_path), width=1920, height=1080)
    )
    assert short.duration_sec == 3.0
    assert Image.open(short.start_frame).size == (1920, 1080)
    long = _book.BookendGenerator().generate(
        _book.BookendRequest("scene_long", "FIRST_FRAME", 40.0, str(tmp_path))
    )
    assert long.duration_sec == 15.0
