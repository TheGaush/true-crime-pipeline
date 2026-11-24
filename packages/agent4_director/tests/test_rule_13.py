"""RULE_13: hero dual prompt_v1 + environmental prompt_v2_safe."""

from __future__ import annotations

from agent4_director.rules.rule_13_dual_prompt import (
    FLOW_HERO_ENGINE,
    Rule13HeroScene,
    validate_rule_13,
)

V1_MOTION = (
    "Figure moves steadily left to right down alley, smooth side tracking shot, "
    "monochrome slate atmosphere, steady pacing, empty alley geometry."
)
V2_RAIN = (
    "Rain reflections ripple across wet pavement, slow panning shot along empty "
    "corridor, fog drifts under a flickering streetlight beam."
)
V2_FLASHLIGHT = (
    "A flashlight beam sweeps across dusty floorboards, slow dolly shot through "
    "empty hallway, swinging door creaks in wind."
)


def hero(
    scene_id: str = "hero_1",
    *,
    prompt_v1: str | None = V1_MOTION,
    prompt_v2_safe: str | None = V2_RAIN,
    prompt_mode: str = "FIRST_FRAME",
    visual_engine: str = FLOW_HERO_ENGINE,
    duration_bucket_sec: int = 8,
) -> Rule13HeroScene:
    return Rule13HeroScene(
        scene_id=scene_id,
        visual_engine=visual_engine,
        prompt_mode=prompt_mode,  # type: ignore[arg-type]
        prompt_v1=prompt_v1,
        prompt_v2_safe=prompt_v2_safe,
        duration_bucket_sec=duration_bucket_sec,
    )


def test_valid_dual_prompts_pass() -> None:
    result = validate_rule_13([hero()])
    assert result.ok


def test_non_hero_scenes_skipped() -> None:
    still = hero(visual_engine="STILL_2K_PANZOOM", prompt_v1=None, prompt_v2_safe=None)
    result = validate_rule_13([still])
    assert result.ok


def test_missing_prompt_v1_fails() -> None:
    result = validate_rule_13([hero(prompt_v1=None)])
    assert not result.ok
    assert any(v.code == "MISSING_PROMPT_V1" for v in result.violations)


def test_missing_prompt_v2_safe_fails() -> None:
    result = validate_rule_13([hero(prompt_v2_safe=None)])
    assert not result.ok
    assert any(v.code == "MISSING_PROMPT_V2_SAFE" for v in result.violations)


def test_v2_struggle_word_fails() -> None:
    bad_v2 = (
        "Rain reflections ripple while a figure struggles with a swinging door, "
        "slow pan across empty corridor, fog under streetlight."
    )
    result = validate_rule_13([hero(prompt_v2_safe=bad_v2)])
    assert any(v.code == "V2_CONFRONTATION_WORD" for v in result.violations)


def test_v2_chase_word_fails() -> None:
    bad_v2 = (
        "A chase echoes through rain-soaked alley reflections, flashlight beam "
        "flickers over wet pavement, fog swirls near empty steps."
    )
    result = validate_rule_13([hero(prompt_v2_safe=bad_v2)])
    assert any(v.code == "V2_CONFRONTATION_WORD" for v in result.violations)


def test_v2_person_confrontation_word_fails() -> None:
    bad_v2 = (
        "Rain drips on empty steps, slow dolly shot through foggy corridor, "
        "streetlight flickers while a suspect hides in shadow."
    )
    result = validate_rule_13([hero(prompt_v2_safe=bad_v2)])
    assert any(
        v.code in {"V2_PERSON_WORD", "V2_CONFRONTATION_WORD", "ANONYMIZER_VIOLATION"}
        for v in result.violations
    )


def test_v2_reuses_struggle_from_v1_fails() -> None:
    v1 = (
        "Silhouette struggles against wind down alley, smooth side tracking shot, "
        "monochrome pacing through charcoal fog, steady camera move."
    )
    v2 = (
        "Rain sweeps empty steps, fog drifts through corridor, the same struggle "
        "ripples across wet pavement under a swinging door shadow."
    )
    result = validate_rule_13([hero(prompt_v1=v1, prompt_v2_safe=v2)])
    assert any(v.code == "V2_REUSES_V1_CONFRONTATION" for v in result.violations)


def test_environmental_flashlight_beam_passes() -> None:
    result = validate_rule_13([hero(prompt_v2_safe=V2_FLASHLIGHT)])
    assert result.ok


def test_first_frame_appearance_noun_in_v2_fails() -> None:
    hooded_v2 = (
        "Rain reflections on pavement, hooded coat draped on railing sways gently, "
        "slow pan along empty corridor, fog under streetlight beam."
    )
    result = validate_rule_13(
        [hero(prompt_mode="FIRST_FRAME", prompt_v2_safe=hooded_v2)]
    )
    assert any(v.code == "APPEARANCE_NOUN_FORBIDDEN" for v in result.violations)


def test_text_to_video_mode_allows_stylized_v1() -> None:
    v1 = (
        "Minimalist 2D stick figure crosses foggy plaza, smooth side tracking shot, "
        "monochrome slate palette, steady atmospheric pacing, empty city block."
    )
    result = validate_rule_13(
        [hero(prompt_mode="TEXT_TO_VIDEO", prompt_v1=v1, prompt_v2_safe=V2_RAIN)]
    )
    assert result.ok


def test_first_and_last_frame_duration_cap() -> None:
    result = validate_rule_13(
        [hero(prompt_mode="FIRST_AND_LAST_FRAME", duration_bucket_sec=12)]
    )
    assert any(v.code == "DURATION_MODE_MISMATCH" for v in result.violations)


def test_tracking_shot_in_v1_not_flagged_by_rule_12() -> None:
    result = validate_rule_13([hero()])
    assert not any(
        v.code == "ANONYMIZER_VIOLATION" and v.field == "prompt_v1"
        for v in result.violations
    )