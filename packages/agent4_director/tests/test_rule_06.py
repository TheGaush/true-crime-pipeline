"""RULE_06: mid-video retention validator (Task 079)."""

from __future__ import annotations

import ast
from pathlib import Path

from agent4_director.rules.rule_06_retention import (
    ACT1_HERO_BUDGET_FRACTION,
    ACT2_WINDOW_END_MS,
    ACT2_WINDOW_START_MS,
    DEFAULT_EPISODE_HERO_BUDGET_MS,
    FOIA_ENGINE,
    HERO_ENGINE,
    OPEN_LOOP_MAX_GAP_MS,
    act1_hero_cap_ms,
    propose_act1_to_act2_reallocation,
    validate_rule_06,
)

RULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent4_director"
    / "rules"
    / "rule_06_retention.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def _hero(
    scene_id: str,
    start_ms: int,
    duration_ms: int,
    *,
    act_number: int = 1,
    emotional_peak_score: float = 0.6,
    retention_peak: bool | None = None,
) -> dict:
    row = {
        "scene_id": scene_id,
        "seq_index": start_ms // 1000,
        "act_number": act_number,
        "visual_engine": HERO_ENGINE,
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "emotional_peak_score": emotional_peak_score,
    }
    if retention_peak is not None:
        row["retention_peak"] = retention_peak
    return row


def _foia(
    scene_id: str,
    start_ms: int,
    duration_ms: int,
    *,
    emotional_peak_score: float = 0.7,
) -> dict:
    return {
        "scene_id": scene_id,
        "seq_index": start_ms // 1000,
        "act_number": 2,
        "visual_engine": FOIA_ENGINE,
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "emotional_peak_score": emotional_peak_score,
        "retention_peak": True,
    }


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(RULE_SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_act1_cap_is_forty_percent_of_episode_hero_budget() -> None:
    cap = act1_hero_cap_ms(DEFAULT_EPISODE_HERO_BUDGET_MS)
    assert cap == int(DEFAULT_EPISODE_HERO_BUDGET_MS * ACT1_HERO_BUDGET_FRACTION)


def test_compliant_manifest_passes_rule_06() -> None:
    cap = act1_hero_cap_ms(DEFAULT_EPISODE_HERO_BUDGET_MS)
    act1_ms = cap - 2_000
    scenes = [
        _hero("intro_a", 10_000, act1_ms // 2, act_number=1),
        _hero("intro_b", 120_000, act1_ms // 2, act_number=1),
        _hero("mid_a", ACT2_WINDOW_START_MS + 30_000, 8_000, act_number=2),
        _foia("mid_f", ACT2_WINDOW_START_MS + 180_000, 12_000),
    ]
    loops = [0, 200_000, 460_000]
    result = validate_rule_06(scenes, open_loops_ms=loops)
    assert result.ok
    assert result.reallocation is None


def test_act1_hero_over_40_percent_fails() -> None:
    cap = act1_hero_cap_ms(DEFAULT_EPISODE_HERO_BUDGET_MS)
    scenes = [
        _hero("heavy", 5_000, cap + 1_000, act_number=1),
        _hero("mid_a", ACT2_WINDOW_START_MS + 10_000, 8_000, act_number=2),
        _hero("mid_b", ACT2_WINDOW_START_MS + 120_000, 8_000, act_number=2),
    ]
    result = validate_rule_06(scenes, open_loops_ms=[0, 200_000])
    assert not result.ok
    assert any(v.code == "ACT1_HERO_BUDGET" for v in result.violations)


def test_act2_window_needs_two_hero_or_foia_peaks() -> None:
    cap = act1_hero_cap_ms(DEFAULT_EPISODE_HERO_BUDGET_MS)
    scenes = [
        _hero("intro", 10_000, cap // 2, act_number=1),
        _hero("solo_peak", ACT2_WINDOW_START_MS + 60_000, 8_000, act_number=2),
    ]
    result = validate_rule_06(scenes, open_loops_ms=[0, 200_000])
    assert any(v.code == "ACT2_PEAK_COUNT" for v in result.violations)


def test_peaks_outside_act2_window_do_not_count() -> None:
    cap = act1_hero_cap_ms(DEFAULT_EPISODE_HERO_BUDGET_MS)
    scenes = [
        _hero("intro", 5_000, cap // 2, act_number=1),
        _hero("early", 300_000, 8_000, act_number=2),
        _hero("late", ACT2_WINDOW_END_MS + 60_000, 8_000, act_number=2),
    ]
    result = validate_rule_06(scenes, open_loops_ms=[0, 200_000])
    assert any(v.code == "ACT2_PEAK_COUNT" for v in result.violations)


def test_open_loops_more_than_4_5_minutes_apart_fail() -> None:
    cap = act1_hero_cap_ms(DEFAULT_EPISODE_HERO_BUDGET_MS)
    scenes = [
        _hero("intro", 5_000, cap // 2, act_number=1),
        _hero("p1", ACT2_WINDOW_START_MS + 10_000, 8_000, act_number=2),
        _foia("p2", ACT2_WINDOW_START_MS + 120_000, 10_000),
    ]
    gap = OPEN_LOOP_MAX_GAP_MS + 5_000
    loops = [0, gap]
    result = validate_rule_06(scenes, open_loops_ms=loops)
    assert any(v.code == "OPEN_LOOP_GAP" for v in result.violations)


def test_intro_heavy_manifest_returns_act1_to_act2_reallocation() -> None:
    cap = act1_hero_cap_ms(DEFAULT_EPISODE_HERO_BUDGET_MS)
    excess = 12_000
    scenes = [
        _hero("intro_low", 5_000, cap // 2, act_number=1, emotional_peak_score=0.3),
        _hero(
            "intro_high",
            100_000,
            cap // 2 + excess,
            act_number=1,
            emotional_peak_score=0.9,
        ),
        _hero("mid_a", ACT2_WINDOW_START_MS + 20_000, 8_000, act_number=2),
        _foia("mid_b", ACT2_WINDOW_START_MS + 150_000, 10_000),
    ]
    realloc = propose_act1_to_act2_reallocation(scenes)
    assert realloc is not None
    assert realloc.from_act == 1
    assert realloc.to_act == 2
    assert realloc.shift_ms == excess
    assert realloc.scene_ids[0] == "intro_low"

    result = validate_rule_06(scenes, open_loops_ms=[0, 200_000])
    assert result.reallocation is not None
    assert result.reallocation.shift_ms == excess
    assert result.reallocation.to_act == 2