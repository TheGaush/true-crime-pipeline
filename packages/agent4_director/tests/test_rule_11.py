"""RULE_11 prompt_mode split compressor tests."""

from __future__ import annotations

from agent4_director.rules.rule_11_prompt_compress import (
    MOTION_WORD_MAX,
    MOTION_WORD_MIN,
    Rule11Scene,
    compress_motion_prompt,
    contains_negative_keyword_ban,
    count_motion_words,
    validate_rule_11,
)

_VALID_MOTION = (
    "Figure moves steadily left-to-right down the alley, "
    "smooth side tracking shot with gradual push in, rain reflections shimmer."
)


def scene(
    scene_id: str,
    prompt_mode: str,
    visual_prompt: str,
    duration_ms: int = 8_000,
) -> Rule11Scene:
    return Rule11Scene(
        scene_id=scene_id,
        prompt_mode=prompt_mode,
        visual_prompt=visual_prompt,
        duration_ms=duration_ms,
    )


def test_first_and_last_frame_strips_hooded_appearance_edge_case() -> None:
    raw = (
        "hooded 2D ink figure moves steadily left-to-right down alley, "
        "smooth side tracking shot."
    )
    compressed = compress_motion_prompt(raw, "FIRST_AND_LAST_FRAME")
    assert compressed == (
        "Figure moves steadily left-to-right down alley, smooth side tracking shot."
    )
    assert "hooded" not in compressed.lower()
    result = validate_rule_11(
        [scene("s1", "FIRST_AND_LAST_FRAME", raw, duration_ms=6_000)]
    )
    assert result.compressed_prompts["s1"] == compressed


def test_first_frame_strips_all_appearance_tokens() -> None:
    prompt = (
        "hooded detective in charcoal coat and fedora walks forward slowly, "
        "static wide shot holds then gentle dolly in toward center path."
    )
    compressed = compress_motion_prompt(prompt, "FIRST_FRAME")
    for word in ("hooded", "detective", "charcoal", "coat", "fedora"):
        assert word not in compressed.lower()
    assert "walks" in compressed.lower()


def test_text_to_video_allows_stylized_subject_label() -> None:
    prompt = (
        "Minimalist 2D stick figure crosses foggy courtyard, "
        "slow crane down reveals wet cobblestones, soft ambient street glow "
        "and distant siren echo."
    )
    assert compress_motion_prompt(prompt, "TEXT_TO_VIDEO") == prompt
    result = validate_rule_11([scene("t1", "TEXT_TO_VIDEO", prompt)])
    assert result.ok


def test_motion_word_count_bounds() -> None:
    short = "Figure drifts slowly left, camera pans gently."
    long = " ".join(["word"] * (MOTION_WORD_MAX + 1))
    assert count_motion_words(_VALID_MOTION) in range(MOTION_WORD_MIN, MOTION_WORD_MAX + 1)

    short_result = validate_rule_11(
        [scene("short", "FIRST_FRAME", short, duration_ms=5_000)]
    )
    assert any(v.code == "MOTION_WORD_COUNT" for v in short_result.violations)

    long_result = validate_rule_11([scene("long", "FIRST_FRAME", long)])
    assert any(v.code == "MOTION_WORD_COUNT" for v in long_result.violations)


def test_negative_keyword_ban() -> None:
    assert contains_negative_keyword_ban("camera holds, no zoom into faces today")
    assert contains_negative_keyword_ban("please don't show blood on pavement")
    assert not contains_negative_keyword_ban("known route continues toward river bend")

    bad = (
        "Minimalist figure drifts forward, no sudden turns at corner, "
        "camera tracks smoothly from the right through alley mist quietly."
    )
    result = validate_rule_11([scene("neg", "TEXT_TO_VIDEO", bad)])
    assert any(v.code == "NEGATIVE_KEYWORD_BAN" for v in result.violations)


def test_duration_buckets_by_prompt_mode() -> None:
    ok_ttv = validate_rule_11(
        [scene("d1", "TEXT_TO_VIDEO", _VALID_MOTION, duration_ms=15_000)]
    )
    assert ok_ttv.ok

    over_ttv = validate_rule_11(
        [scene("d2", "TEXT_TO_VIDEO", _VALID_MOTION, duration_ms=16_000)]
    )
    assert any(v.code == "DURATION_OUT_OF_RANGE" for v in over_ttv.violations)

    over_2f = validate_rule_11(
        [
            scene(
                "d3",
                "FIRST_AND_LAST_FRAME",
                _VALID_MOTION,
                duration_ms=11_000,
            )
        ]
    )
    assert any(v.code == "DURATION_OUT_OF_RANGE" for v in over_2f.violations)

    under = validate_rule_11(
        [scene("d4", "FIRST_FRAME", _VALID_MOTION, duration_ms=2_500)]
    )
    assert any(v.code == "DURATION_OUT_OF_RANGE" for v in under.violations)


def test_rejects_retired_prompt_modes() -> None:
    for retired in ("FRAMES_MOTION_ONLY", "VEO_3_1_LITE"):
        result = validate_rule_11(
            [scene("r1", retired, _VALID_MOTION, duration_ms=5_000)]
        )
        assert any(v.code == "RETIRED_PROMPT_MODE" for v in result.violations)

    drift = validate_rule_11(
        [
            scene(
                "r2",
                "TEXT_TO_VIDEO",
                "Use Veo 3.1 Lite mode for this alley beat with tracking shot.",
                duration_ms=6_000,
            )
        ]
    )
    assert any(v.code == "RETIRED_PROMPT_TEXT" for v in drift.violations)


def test_valid_first_frame_passes_rule_11() -> None:
    prompt = _VALID_MOTION
    result = validate_rule_11(
        [scene("ok", "FIRST_FRAME", prompt, duration_ms=8_000)]
    )
    assert result.ok
    assert result.compressed_prompts["ok"] == prompt