"""LAW_04: pre-locked spatial anchors & pursuit travel_axis continuity (Task 083)."""

from __future__ import annotations

import ast
from pathlib import Path

from agent4_director.rules.law_04_spatial import (
    LAW_ID,
    STILL_ENGINE,
    Law04Result,
    validate_law_04,
)

LAW_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent4_director"
    / "rules"
    / "law_04_spatial.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def _locked_anchor(
    anchor_id: str,
    *,
    still_id: str = "still_0",
    span_cols: float = 1.5,
    span_rows: float = 2.0,
    lock_status: str = "LOCKED",
) -> dict:
    return {
        "anchor_id": anchor_id,
        "episode_id": "ep_1",
        "still_2k_id": still_id,
        "clue_name": "overturned table",
        "grid_cell": "A1",
        "span_cols": span_cols,
        "span_rows": span_rows,
        "x_px": 128,
        "y_px": 72,
        "target_zoom": 2.5,
        "travel_axis": "STATIC",
        "lock_status": lock_status,
        "locked_by": "editor_1",
        "locked_at": 100,
        "still_asset_sha256": "a" * 64,
    }


def _still(still_id: str, *, illustrative: int = 1) -> dict:
    return {
        "still_2k_id": still_id,
        "episode_id": "ep_1",
        "asset_path": "/plates/still.png",
        "asset_sha256": "b" * 64,
        "width_px": 2560,
        "height_px": 1440,
        "is_illustrative_reconstruction": illustrative,
        "disclaimer_label_text": "ILLUSTRATIVE RECONSTRUCTION — NOT CRIME SCENE PHOTO",
        "created_at": 1,
    }


def _still_scene(
    scene_id: str,
    seq_index: int,
    anchor_id: str,
    *,
    start_ms: int = 0,
    duration_ms: int = 6_000,
) -> dict:
    return {
        "scene_id": scene_id,
        "seq_index": seq_index,
        "act_number": 1,
        "visual_engine": STILL_ENGINE,
        "motif_component": "Illustrative2KPanZoom",
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "timeline_spec_json": {
            "visual_engine": STILL_ENGINE,
            "motif_component": "Illustrative2KPanZoom",
            "prompt_mode": "NONE",
            "anchor_id": anchor_id,
            "still_2k_id": "still_0",
            "fps": 30,
            "start_frame": 0,
            "duration_frames": 180,
        },
        "fallback_spec_json": None,
    }


def _pursuit_scene(
    scene_id: str,
    seq_index: int,
    travel_axis: str,
    *,
    start_ms: int = 0,
    duration_ms: int = 8_000,
) -> dict:
    return {
        "scene_id": scene_id,
        "seq_index": seq_index,
        "act_number": 2,
        "visual_engine": "FLOW_HERO_VIDEO",
        "motif_component": "HeroVideoBridge",
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "timeline_spec_json": {
            "visual_engine": "FLOW_HERO_VIDEO",
            "motif_component": "HeroVideoBridge",
            "prompt_mode": "TEXT_TO_VIDEO",
            "travel_axis": travel_axis,
            "pursuit_scene": True,
            "anchor_id": None,
            "still_2k_id": None,
            "fps": 30,
            "start_frame": 0,
            "duration_frames": 240,
        },
        "fallback_spec_json": None,
    }


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(LAW_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_still_scene_passes_locked_illustrative_anchor() -> None:
    scenes = [_still_scene("s1", 1, "anc_ok")]
    anchors = [_locked_anchor("anc_ok")]
    stills = [_still("still_0")]
    result = validate_law_04(scenes, anchors, stills)
    assert isinstance(result, Law04Result)
    assert result.ok


def test_missing_anchor_returns_anchor_id() -> None:
    scenes = [_still_scene("s1", 1, "anc_missing")]
    result = validate_law_04(scenes, [], [_still("still_0")])
    assert not result.ok
    assert result.missing_anchor_ids == ["anc_missing"]
    assert any(v.code == "MISSING_ANCHOR" and v.anchor_id == "anc_missing" for v in result.violations)


def test_unlocked_anchor_fails() -> None:
    scenes = [_still_scene("s1", 1, "anc_draft")]
    anchors = [_locked_anchor("anc_draft", lock_status="DRAFT")]
    result = validate_law_04(scenes, anchors, [_still("still_0")])
    assert any(v.code == "ANCHOR_NOT_LOCKED" for v in result.violations)


def test_still_must_be_illustrative_reconstruction() -> None:
    scenes = [_still_scene("s1", 1, "anc_ok")]
    anchors = [_locked_anchor("anc_ok")]
    stills = [_still("still_0", illustrative=0)]
    result = validate_law_04(scenes, anchors, stills)
    assert any(v.code == "STILL_NOT_ILLUSTRATIVE" for v in result.violations)


def test_anchor_requires_span_cols_and_rows() -> None:
    anchor = _locked_anchor("anc_ok")
    del anchor["span_cols"]
    scenes = [_still_scene("s1", 1, "anc_ok")]
    result = validate_law_04(scenes, [anchor], [_still("still_0")])
    assert any(v.code == "ANCHOR_SPAN_MISSING" for v in result.violations)


def test_consecutive_pursuit_same_axis_passes() -> None:
    scenes = [
        _pursuit_scene("p1", 1, "L_TO_R", start_ms=0),
        _pursuit_scene("p2", 2, "L_TO_R", start_ms=10_000),
    ]
    result = validate_law_04(scenes, [], [])
    assert result.ok


def test_consecutive_pursuit_axis_flip_fails() -> None:
    scenes = [
        _pursuit_scene("p1", 1, "L_TO_R", start_ms=0),
        _pursuit_scene("p2", 2, "R_TO_L", start_ms=10_000),
    ]
    result = validate_law_04(scenes, [], [])
    assert not result.ok
    assert any(v.code == "TRAVEL_AXIS_FLIP" for v in result.violations)


def test_non_consecutive_pursuit_axis_flip_allowed() -> None:
    scenes = [
        _pursuit_scene("p1", 1, "L_TO_R", start_ms=0),
        {
            "scene_id": "gap",
            "seq_index": 2,
            "visual_engine": "CODE_STICKMAN",
            "start_ms": 10_000,
            "end_ms": 15_000,
            "timeline_spec_json": {"visual_engine": "CODE_STICKMAN", "prompt_mode": "NONE"},
        },
        _pursuit_scene("p2", 3, "R_TO_L", start_ms=20_000),
    ]
    result = validate_law_04(scenes, [], [])
    assert result.ok


def test_law_id_constant() -> None:
    assert LAW_ID == "LAW_04"