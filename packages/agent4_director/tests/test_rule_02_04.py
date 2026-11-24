"""RULE_02 act-constrained budget downgrade & RULE_04 non-neighbor fallbacks (Task 077)."""

from __future__ import annotations

import ast
from pathlib import Path

from agent4_director.rules.rule_02_04_budget import (
    ACT2_PEAKS_TO_PROTECT,
    DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD,
    DEFAULT_MAX_HERO_CLIPS,
    DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD,
    HERO_ENGINE,
    MAX_ENGINE_STREAK_MS,
    STICKMAN_ENGINE,
    STILL_ENGINE,
    BudgetCaps,
    apply_act_constrained_downgrade,
    assign_rule_04_fallbacks,
    estimate_hero_cost_micro_usd,
    fallback_streak_ms_if_activated,
    load_budget_caps,
    protected_hero_scene_ids,
    select_non_neighbor_fallback_engine,
    validate_rule_02,
    validate_rule_02_and_04,
    validate_rule_04,
)

REPO = Path(__file__).resolve().parents[3]
RULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent4_director"
    / "rules"
    / "rule_02_04_budget.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}


def _hero(
    scene_id: str,
    seq_index: int,
    *,
    act_number: int = 1,
    start_ms: int,
    duration_ms: int = 8000,
    emotional_peak_score: float = 0.35,
) -> dict:
    return {
        "scene_id": scene_id,
        "seq_index": seq_index,
        "act_number": act_number,
        "visual_engine": HERO_ENGINE,
        "motif_component": "HeroVideoBridge",
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "emotional_peak_score": emotional_peak_score,
        "timeline_spec_json": {
            "visual_engine": HERO_ENGINE,
            "motif_component": "HeroVideoBridge",
            "prompt_mode": "TEXT_TO_VIDEO",
        },
        "fallback_spec_json": None,
    }


def _stickman(scene_id: str, seq_index: int, start_ms: int, duration_ms: int = 40_000) -> dict:
    return {
        "scene_id": scene_id,
        "seq_index": seq_index,
        "act_number": 2,
        "visual_engine": STICKMAN_ENGINE,
        "motif_component": "StickmanStage",
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "emotional_peak_score": 0.35,
        "timeline_spec_json": {
            "visual_engine": STICKMAN_ENGINE,
            "motif_component": "StickmanStage",
            "prompt_mode": "NONE",
        },
        "fallback_spec_json": None,
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


def test_load_budget_caps_from_providers_yaml() -> None:
    caps = load_budget_caps(REPO / "providers.yaml")
    assert caps.max_hero_clips == DEFAULT_MAX_HERO_CLIPS
    assert caps.episode_video_cap_micro_usd == DEFAULT_EPISODE_VIDEO_CAP_MICRO_USD
    assert caps.monthly_all_providers_cap_micro_usd == DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD


def test_rule_02_downgrades_excess_hero_clips() -> None:
    scenes = [_hero(f"h{i}", i, start_ms=i * 10_000) for i in range(12)]
    result = validate_rule_02(scenes, auto_downgrade=True)
    assert result.passed
    assert result.scenes is not None
    remaining = [s for s in result.scenes if s["visual_engine"] == HERO_ENGINE]
    assert len(remaining) == DEFAULT_MAX_HERO_CLIPS


def test_rule_02_protects_cold_open_and_act2_top_peaks() -> None:
    scenes: list[dict] = [
        _hero("cold", 0, act_number=1, start_ms=5_000, emotional_peak_score=0.2),
    ]
    for i in range(1, 11):
        scenes.append(
            _hero(
                f"a2_low_{i}",
                i,
                act_number=2,
                start_ms=100_000 + i * 10_000,
                emotional_peak_score=0.1 + i * 0.01,
            )
        )
    scenes.append(
        _hero("a2_peak_a", 20, act_number=2, start_ms=500_000, emotional_peak_score=0.95)
    )
    scenes.append(
        _hero("a2_peak_b", 21, act_number=2, start_ms=510_000, emotional_peak_score=0.90)
    )
    scenes.append(_hero("extra", 22, act_number=3, start_ms=800_000, emotional_peak_score=0.05))

    protected = protected_hero_scene_ids(scenes)
    assert "cold" in protected
    assert "a2_peak_a" in protected
    assert "a2_peak_b" in protected

    out = apply_act_constrained_downgrade(scenes)
    heroes = {s["scene_id"]: s for s in out if s["visual_engine"] == HERO_ENGINE}
    assert "cold" in heroes
    assert "a2_peak_a" in heroes
    assert "a2_peak_b" in heroes
    assert "extra" not in heroes


def test_rule_02_enforces_episode_and_monthly_caps() -> None:
    duration_ms = 8000
    scenes = [_hero(f"h{i}", i, start_ms=i * duration_ms, duration_ms=duration_ms) for i in range(10)]
    cost = estimate_hero_cost_micro_usd(scenes, usd_per_sec=0.10)
    assert cost == 8_000_000

    caps = BudgetCaps(episode_video_cap_micro_usd=cost)
    monthly_spend = DEFAULT_MONTHLY_ALL_PROVIDERS_CAP_MICRO_USD - 500_000
    result = validate_rule_02(
        scenes,
        caps=caps,
        monthly_spend_micro_usd=monthly_spend,
        auto_downgrade=False,
    )
    assert not result.passed
    codes = {v.code for v in result.violations}
    assert "EPISODE_VIDEO_CAP" in codes or "MONTHLY_ALL_PROVIDERS" in codes


def test_rule_02_downgrades_duration_over_80s() -> None:
    scenes = [_hero(f"h{i}", i, start_ms=i * 8000, duration_ms=8000) for i in range(11)]
    result = validate_rule_02(scenes, auto_downgrade=True)
    assert result.passed
    total_ms = sum(
        s["end_ms"] - s["start_ms"]
        for s in (result.scenes or [])
        if s["visual_engine"] == HERO_ENGINE
    )
    assert total_ms <= 80_000


def test_rule_04_stickman_sandwich_uses_still_2k() -> None:
    engine = select_non_neighbor_fallback_engine(STICKMAN_ENGINE, STICKMAN_ENGINE)
    assert engine == STILL_ENGINE

    scenes = [
        _stickman("s1", 0, 0, 30_000),
        _hero("hero", 1, act_number=2, start_ms=30_000, duration_ms=8000),
        _stickman("s3", 2, 38_000, 30_000),
    ]
    assigned = assign_rule_04_fallbacks(scenes)
    fb = assigned[1]["fallback_spec_json"]
    assert fb["engine"] == STILL_ENGINE
    assert fb["rule"] == "RULE_04"

    check = validate_rule_04(scenes, auto_assign=True)
    assert check.passed


def test_rule_04_fallback_differs_from_neighbors() -> None:
    scenes = [
        _stickman("s1", 0, 0),
        _hero("hero", 1, act_number=2, start_ms=50_000),
        {
            **_stickman("s3", 2, 100_000),
            "visual_engine": STILL_ENGINE,
            "motif_component": "Illustrative2KPanZoom",
        },
    ]
    result = validate_rule_04(scenes, auto_assign=True)
    assert result.passed
    hero = next(s for s in (result.scenes or []) if s["scene_id"] == "hero")
    fb = hero["fallback_spec_json"]["engine"]
    assert fb != STICKMAN_ENGINE
    assert fb != STILL_ENGINE
    assert fb != HERO_ENGINE


def test_rule_04_two_strike_fallback_streak_under_50s() -> None:
    scenes = [
        _stickman("pre", 0, 0, 40_000),
        _hero("hero", 1, act_number=2, start_ms=40_000, duration_ms=8000),
        _stickman("post", 2, 48_000, 40_000),
    ]
    assigned = assign_rule_04_fallbacks(scenes)
    streak = fallback_streak_ms_if_activated(assigned, 1)
    assert streak <= MAX_ENGINE_STREAK_MS
    assert validate_rule_04(scenes, auto_assign=True).passed


def test_rule_04_flags_neighbor_collision() -> None:
    scenes = [
        _stickman("s1", 0, 0),
        _hero("hero", 1, act_number=2, start_ms=50_000),
        _stickman("s3", 2, 100_000),
    ]
    scenes[1]["fallback_spec_json"] = {
        "engine": STICKMAN_ENGINE,
        "motif_component": "StickmanStage",
        "rule": "RULE_04",
    }
    result = validate_rule_04(scenes, auto_assign=False)
    assert not result.passed
    assert any(v.code in {"NEIGHBOR_PREV", "NEIGHBOR_NEXT"} for v in result.violations)


def test_act2_keeps_at_least_two_hero_peaks_after_downgrade() -> None:
    scenes: list[dict] = []
    for i in range(2):
        scenes.append(
            _hero(
                f"peak_{i}",
                i,
                act_number=2,
                start_ms=200_000 + i * 10_000,
                emotional_peak_score=0.9 - i * 0.05,
            )
        )
    for i in range(10):
        scenes.append(
            _hero(
                f"filler_{i}",
                10 + i,
                act_number=3,
                start_ms=400_000 + i * 10_000,
                emotional_peak_score=0.1,
            )
        )

    result = validate_rule_02(scenes, auto_downgrade=True)
    assert result.passed
    act2_heroes = [
        s
        for s in (result.scenes or [])
        if s["visual_engine"] == HERO_ENGINE and s["act_number"] == 2
    ]
    assert len(act2_heroes) >= ACT2_PEAKS_TO_PROTECT


def test_validate_rule_02_and_04_joint_pass() -> None:
    scenes = [
        _stickman("s1", 0, 0, 30_000),
        _hero("h1", 1, act_number=2, start_ms=30_000, emotional_peak_score=0.95),
        _stickman("s3", 2, 38_000, 30_000),
        _hero("h2", 3, act_number=2, start_ms=68_000, emotional_peak_score=0.90),
        _stickman("s5", 4, 76_000, 30_000),
    ]
    r02, r04 = validate_rule_02_and_04(scenes)
    assert r02.passed
    assert r04.passed