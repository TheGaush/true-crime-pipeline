"""Tests for RULE_12 cinematography bigram whitelist and split metaphor tables."""

from __future__ import annotations

from agent4_director.rules.rule_12_anonymizer import (
    CINEMATOGRAPHY_BIGRAM_WHITELIST,
    find_blocked_safety_terms,
    mask_cinematography_bigrams,
    rule_12_passes,
    check_rule_12,
)

TRACKING_MOTION = (
    "Figure moves steadily left-to-right down alley, smooth side tracking shot."
)
VIOLENT_SHOT = "The suspect shot the victim near the loading dock."
SILHOUETTE_T2V = (
    "Rainlit alley with atmospheric stylized silhouette drifting forward, slow wide shot."
)


def test_mask_cinematography_bigrams_covers_canonical_list() -> None:
    for bigram in CINEMATOGRAPHY_BIGRAM_WHITELIST:
        masked = mask_cinematography_bigrams(f"hold a {bigram} on the door")
        assert bigram not in masked


def test_smooth_side_tracking_shot_has_no_blocked_terms() -> None:
    assert find_blocked_safety_terms(TRACKING_MOTION) == ()
    assert rule_12_passes(TRACKING_MOTION, "FIRST_FRAME")


def test_each_whitelisted_bigram_clears_shot_token() -> None:
    for bigram in CINEMATOGRAPHY_BIGRAM_WHITELIST:
        assert find_blocked_safety_terms(f"hold a {bigram} on the corridor") == ()


def test_person_shot_phrase_is_blocked() -> None:
    assert "shot" in find_blocked_safety_terms(VIOLENT_SHOT)
    report = check_rule_12(VIOLENT_SHOT, "TEXT_TO_VIDEO")
    assert report.passed is False
    assert any(f.blocked_terms and "shot" in f.blocked_terms for f in report.findings)


def test_gun_and_minor_terms_blocked() -> None:
    assert find_blocked_safety_terms("officers recovered a gun from the scene") == ("gun",)
    assert find_blocked_safety_terms("interviewed a minor witness") == ("minor",)
    assert find_blocked_safety_terms("suspect began shooting before fleeing") == ("shooting",)


def test_shooting_tracking_shot_allowed() -> None:
    text = "We open on a shooting tracking shot across the evidence board."
    assert find_blocked_safety_terms(text) == ()
    assert rule_12_passes(text, "FIRST_FRAME")


def test_text_to_video_allows_stylized_silhouette() -> None:
    assert rule_12_passes(SILHOUETTE_T2V, "TEXT_TO_VIDEO")
    report = check_rule_12(SILHOUETTE_T2V, "TEXT_TO_VIDEO")
    assert report.passed is True


def test_text_to_video_rejects_hooded_appearance() -> None:
    prompt = "Hooded detective crosses rain alley, charcoal coat, medium shot."
    assert rule_12_passes(prompt, "TEXT_TO_VIDEO") is False
    report = check_rule_12(prompt, "TEXT_TO_VIDEO")
    assert any("hooded" in f.blocked_terms for f in report.findings)


def test_first_frame_rejects_appearance_nouns() -> None:
    prompt = "Hooded ink figure in charcoal coat, slow tracking shot."
    assert rule_12_passes(prompt, "FIRST_FRAME") is False


def test_first_frame_allows_motion_and_camera_only() -> None:
    prompt = "Glides forward through doorway, panning shot, steady lateral move."
    assert rule_12_passes(prompt, "FIRST_FRAME")


def test_first_and_last_frame_uses_same_metaphor_table() -> None:
    assert rule_12_passes(TRACKING_MOTION, "FIRST_AND_LAST_FRAME")


def test_unsupported_prompt_mode_fails() -> None:
    report = check_rule_12(TRACKING_MOTION, "FRAMES_MOTION_ONLY")
    assert report.passed is False
    assert any("unsupported prompt_mode" in f.message for f in report.findings)