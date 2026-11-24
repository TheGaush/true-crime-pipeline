"""RULE_05: micro-beat clock, engine streaks, and CaseBoardSpine boundaries."""

from __future__ import annotations

from agent4_director.rules.rule_05_interrupt import (
    FLOW_HERO_EXEMPT_MAX_MS,
    Foia911Slot,
    Rule05Scene,
    Rule05Timeline,
    is_flow_motion_exempt,
    validate_rule_05,
)


def scene(
    scene_id: str,
    engine: str,
    start_ms: int,
    duration_ms: int,
    motif: str = "StickmanStage",
) -> Rule05Scene:
    return Rule05Scene(
        scene_id=scene_id,
        visual_engine=engine,
        motif_component=motif,
        start_ms=start_ms,
        end_ms=start_ms + duration_ms,
    )


def test_flow_hero_8s_exempt_from_micro_beat_clock() -> None:
    hero = scene("h1", "FLOW_HERO_VIDEO", 0, 8_000, motif="HeroVideoBridge")
    assert is_flow_motion_exempt(hero)
    result = validate_rule_05(Rule05Timeline(scenes=[hero]))
    assert result.ok


def test_code_8s_fails_micro_beat() -> None:
    code = scene("c1", "CODE_STICKMAN", 0, 8_000)
    result = validate_rule_05(Rule05Timeline(scenes=[code]))
    assert not result.ok
    assert any(v.code == "MICRO_BEAT_EXCEEDED" for v in result.violations)


def test_still_2k_6s_passes_micro_beat() -> None:
    still = scene("k1", "STILL_2K_PANZOOM", 0, 6_000, motif="Illustrative2KPanZoom")
    result = validate_rule_05(Rule05Timeline(scenes=[still]))
    assert result.ok


def test_still_2k_6200ms_fails_micro_beat() -> None:
    still = scene("k2", "STILL_2K_PANZOOM", 0, 6_200, motif="Illustrative2KPanZoom")
    result = validate_rule_05(Rule05Timeline(scenes=[still]))
    assert any(v.code == "MICRO_BEAT_EXCEEDED" for v in result.violations)


def test_engine_streak_at_50s_passes() -> None:
    scenes = [
        scene(f"c{i}", "CODE_STICKMAN", i * 5_000, 5_000) for i in range(10)
    ]
    result = validate_rule_05(Rule05Timeline(scenes=scenes))
    assert result.ok


def test_engine_streak_over_50s_fails() -> None:
    scenes = [
        scene(f"c{i}", "CODE_STICKMAN", i * 5_000, 5_000) for i in range(11)
    ]
    result = validate_rule_05(Rule05Timeline(scenes=scenes))
    assert any(v.code == "ENGINE_STREAK_EXCEEDED" for v in result.violations)


def test_case_board_spine_in_window_on_scene_boundary() -> None:
    scenes: list[Rule05Scene] = []
    cursor = 0
    for i in range(40):
        if i % 2 == 0:
            scenes.append(
                scene(
                    f"p{i}",
                    "STILL_2K_PANZOOM",
                    cursor,
                    6_000,
                    motif="Illustrative2KPanZoom",
                )
            )
        else:
            scenes.append(scene(f"p{i}", "CODE_STICKMAN", cursor, 6_000))
        cursor += 6_000
    scenes.append(
        scene("spine", "CODE_STICKMAN", 240_000, 6_000, motif="CaseBoardSpine")
    )
    result = validate_rule_05(Rule05Timeline(scenes=scenes))
    assert result.ok


def test_case_board_spine_before_210s_fails() -> None:
    scenes = [
        scene("pre", "CODE_STICKMAN", 0, 200_000),
        scene("spine", "CODE_STICKMAN", 200_000, 6_000, motif="CaseBoardSpine"),
    ]
    result = validate_rule_05(Rule05Timeline(scenes=scenes))
    assert any(v.code == "SPINE_WINDOW" for v in result.violations)


def test_case_board_spine_after_270s_fails() -> None:
    scenes = [
        scene("pre", "CODE_STICKMAN", 0, 275_000),
        scene("spine", "CODE_STICKMAN", 275_000, 6_000, motif="CaseBoardSpine"),
    ]
    result = validate_rule_05(Rule05Timeline(scenes=scenes))
    assert any(v.code == "SPINE_WINDOW" for v in result.violations)


def test_case_board_spine_mid_911_fails() -> None:
    """911 from 3:50–4:15; spine at 4:00 mid-call must fail."""
    slot = Foia911Slot(start_ms=230_000, end_ms=255_000)
    scenes = [
        scene("pre", "FOIA_REAL_FOOTAGE", 0, 240_000),
        scene("spine", "CODE_STICKMAN", 240_000, 6_000, motif="CaseBoardSpine"),
    ]
    result = validate_rule_05(
        Rule05Timeline(scenes=scenes, foia_911_slots_ms=[slot])
    )
    assert any(v.code == "SPINE_MID_911" for v in result.violations)


def test_case_board_spine_snaps_to_911_end_passes() -> None:
    """911 ends at 4:15 (255s), inside the 210–270s flexible window."""
    slot = Foia911Slot(start_ms=230_000, end_ms=255_000)
    scenes = [
        scene("call", "FOIA_REAL_FOOTAGE", 230_000, 25_000),
        scene("spine", "CODE_STICKMAN", 255_000, 6_000, motif="CaseBoardSpine"),
    ]
    result = validate_rule_05(
        Rule05Timeline(scenes=scenes, foia_911_slots_ms=[slot])
    )
    assert result.ok


def test_case_board_spine_on_sentence_boundary_passes() -> None:
    scenes = [
        scene("spine", "CODE_STICKMAN", 222_000, 6_000, motif="CaseBoardSpine"),
    ]
    result = validate_rule_05(
        Rule05Timeline(scenes=scenes, sentence_boundaries_ms=[222_000])
    )
    assert result.ok


def test_case_board_spine_off_boundary_fails() -> None:
    scenes = [
        scene("spine", "CODE_STICKMAN", 222_500, 6_000, motif="CaseBoardSpine"),
    ]
    result = validate_rule_05(
        Rule05Timeline(scenes=scenes, sentence_boundaries_ms=[222_000])
    )
    assert any(v.code == "SPINE_BOUNDARY" for v in result.violations)


def test_flow_hero_exempt_max_is_10s() -> None:
    assert FLOW_HERO_EXEMPT_MAX_MS == 10_000
    at_cap = scene("h_cap", "FLOW_HERO_VIDEO", 0, 10_000, motif="HeroVideoBridge")
    assert is_flow_motion_exempt(at_cap)
    over = scene("h_over", "FLOW_HERO_VIDEO", 0, 10_001, motif="HeroVideoBridge")
    assert not is_flow_motion_exempt(over)
    result = validate_rule_05(Rule05Timeline(scenes=[over]))
    assert result.ok