"""DirectorCompiler diff-repair loop & fixed-point lint (Task 088)."""

from __future__ import annotations

import copy

from agent4_director.compiler_loop import (
    MAX_REPAIR_PASSES,
    RULE_COUNT,
    BudgetCaps,
    DirectorCompiler,
    apply_deterministic_downgrade,
    apply_repair_hints,
    make_broken_repair_fn,
    make_stubborn_repair_fn,
    protected_hero_scene_ids,
    split_flow_beat_ms,
)

HERO = "FLOW_HERO_VIDEO"
STICKMAN = "CODE_STICKMAN"


def _hero(
    scene_id: str,
    seq_index: int,
    *,
    act_number: int = 2,
    start_ms: int,
    duration_ms: int = 8000,
    emotional_peak_score: float = 0.5,
    fallback: dict | None = None,
) -> dict:
    return {
        "scene_id": scene_id,
        "seq_index": seq_index,
        "act_number": act_number,
        "visual_engine": HERO,
        "motif_component": "HeroVideoBridge",
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "emotional_peak_score": emotional_peak_score,
        "timeline_spec_json": {
            "visual_engine": HERO,
            "motif_component": "HeroVideoBridge",
            "prompt_mode": "TEXT_TO_VIDEO",
        },
        "fallback_spec_json": fallback,
    }


def _stickman(scene_id: str, seq_index: int, start_ms: int, duration_ms: int = 30_000) -> dict:
    return {
        "scene_id": scene_id,
        "seq_index": seq_index,
        "act_number": 2,
        "visual_engine": STICKMAN,
        "motif_component": "StickmanStage",
        "start_ms": start_ms,
        "end_ms": start_ms + duration_ms,
        "emotional_peak_score": 0.2,
        "timeline_spec_json": {
            "visual_engine": STICKMAN,
            "motif_component": "StickmanStage",
            "prompt_mode": "NONE",
        },
        "fallback_spec_json": None,
    }


def test_split_flow_beat_9_2s_is_6_plus_3_2() -> None:
    flow_ms, code_ms = split_flow_beat_ms(9200)
    assert flow_ms == 6000
    assert code_ms == 3200


def test_compiler_downgrade_splits_9_2s_beat() -> None:
    scenes = [
        _stickman("s0", 0, 0, 60_000),
        _hero("beat", 1, start_ms=60_000, duration_ms=9200, fallback=None),
        _stickman("s2", 2, 69_200, 30_000),
    ]
    out = apply_deterministic_downgrade(scenes)
    heroes = [s for s in out if s["visual_engine"] == HERO]
    codes = [s for s in out if s["scene_id"] == "beat_code"]
    assert len(heroes) == 1
    assert heroes[0]["end_ms"] - heroes[0]["start_ms"] == 6000
    assert len(codes) == 1
    assert codes[0]["end_ms"] - codes[0]["start_ms"] == 3200


def test_act2_top_two_peaks_survive_downgrade() -> None:
    scenes: list[dict] = [
        _hero("cold", 0, act_number=1, start_ms=5_000, emotional_peak_score=0.2),
    ]
    for i in range(1, 11):
        scenes.append(
            _hero(
                f"low_{i}",
                i,
                act_number=2,
                start_ms=100_000 + i * 10_000,
                emotional_peak_score=0.1 + i * 0.01,
            )
        )
    scenes.append(
        _hero("peak_a", 20, act_number=2, start_ms=500_000, emotional_peak_score=0.95)
    )
    scenes.append(
        _hero("peak_b", 21, act_number=2, start_ms=510_000, emotional_peak_score=0.90)
    )
    scenes.append(
        _hero("extra", 22, act_number=3, start_ms=800_000, emotional_peak_score=0.05)
    )

    protected = protected_hero_scene_ids(scenes)
    assert "peak_a" in protected
    assert "peak_b" in protected

    out = apply_deterministic_downgrade(scenes)
    hero_ids = {s["scene_id"] for s in out if s["visual_engine"] == HERO}
    assert "peak_a" in hero_ids
    assert "peak_b" in hero_ids
    assert "extra" not in hero_ids


def test_fallback_engines_differ_from_neighbors() -> None:
    scenes = [
        _stickman("a", 0, 0),
        _hero("mid", 1, start_ms=30_000, fallback={"engine": STICKMAN}),
        _stickman("b", 2, 38_000),
    ]
    out = apply_deterministic_downgrade(scenes)
    hero = next(s for s in out if s["scene_id"] in ("mid", "mid_flow"))
    fb = hero["fallback_spec_json"]
    assert fb is not None
    assert fb["engine"] != STICKMAN


def test_fixed_point_final_lint_zero_violations() -> None:
    draft = {
        "scenes": [
            _stickman("a", 0, 0),
            _hero("long", 1, start_ms=30_000, duration_ms=9200),
            _stickman("b", 2, 39_200),
        ]
    }
    compiler = DirectorCompiler()
    result = compiler.compile(draft)
    assert result.ok
    assert result.final_lint.all_passed
    assert result.final_lint.violations == []
    assert result.final_lint.passed_rule_count == RULE_COUNT
    assert result.final_lint.rules_summary == f"{RULE_COUNT}/{RULE_COUNT}"


def test_stubborn_repair_passes_on_third_attempt() -> None:
    bad = [
        _stickman("a", 0, 0),
        _hero("long", 1, start_ms=30_000, duration_ms=9200),
        _stickman("b", 2, 39_200),
    ]
    draft = {"scenes": bad}
    repair = make_stubborn_repair_fn(apply_repair_hints)
    compiler = DirectorCompiler(repair_fn=repair)
    result = compiler.compile(draft)
    assert result.ok
    assert result.repair_attempts == 3
    assert not result.used_downgrade
    assert result.final_lint.all_passed


def test_broken_repair_still_converges_via_downgrade() -> None:
    """Repairs noop; deterministic downgrade still reaches 13/13."""
    draft = {
        "scenes": [
            _stickman("a", 0, 0),
            _hero("long", 1, start_ms=30_000, duration_ms=9200),
            _stickman("b", 2, 39_200),
        ]
    }
    compiler = DirectorCompiler(repair_fn=make_broken_repair_fn())
    result = compiler.compile(draft)
    assert result.ok
    assert result.repair_attempts == MAX_REPAIR_PASSES
    assert result.used_downgrade
    assert result.final_lint.violations == []


def test_unfixable_manifest_fails_after_repairs_and_downgrade() -> None:
    scenes = [
        _stickman("a", 0, 0),
        {
            **_hero("x", 1, start_ms=30_000),
            "_force_rule_failure": "RULE_13",
        },
    ]
    draft = {"scenes": scenes}
    compiler = DirectorCompiler(repair_fn=make_broken_repair_fn())
    result = compiler.compile(draft)
    assert not result.ok
    assert any(v.rule_id == "RULE_13" for v in result.final_lint.violations)


def test_repair_attempts_capped_at_three() -> None:
    attempts: list[int] = []

    def counting_repair(
        scenes: list[dict],
        _violations: list,
        attempt: int,
    ) -> list[dict]:
        attempts.append(attempt)
        return copy.deepcopy(scenes)

    draft = {
        "scenes": [
            _stickman("a", 0, 0),
            _hero("long", 1, start_ms=30_000, duration_ms=9200),
        ]
    }
    DirectorCompiler(repair_fn=counting_repair).compile(draft)
    assert attempts == [0, 1, 2]