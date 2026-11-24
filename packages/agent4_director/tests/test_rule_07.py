"""RULE_07: 12-Word Glance hold time and CSS safe-zone contract (Task 080)."""

from __future__ import annotations

import ast
from pathlib import Path

from agent4_director.rules.rule_07_safe_zone import (
    MAX_WORD_COUNT,
    REQUIRED_SAFE_ZONE_MODE,
    Rule07CalloutCard,
    count_words,
    min_hold_duration_sec,
    validate_callout_card,
    validate_rule_07,
)

RULE_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent4_director"
    / "rules"
    / "rule_07_safe_zone.py"
)
_BANNED_TERMS = {
    "PIL",
    "ImageFont",
    "textwrap",
    "font",
    "pixel",
    "wrap_width",
    "cv2",
}


def card_2k(
    card_id: str,
    headline: str,
    duration_sec: float,
    *,
    x: int = 640,
    y: int = 480,
    safe_zone_mode: str = REQUIRED_SAFE_ZONE_MODE,
) -> Rule07CalloutCard:
    return Rule07CalloutCard(
        card_id=card_id,
        headline=headline,
        duration_sec=duration_sec,
        safe_zone_mode=safe_zone_mode,
        anchor_space="STILL_2K",
        anchor_x_px=x,
        anchor_y_px=y,
    )


def card_stage(
    card_id: str,
    headline: str,
    duration_sec: float,
    *,
    x: float = 960.0,
    y: float = 540.0,
    safe_zone_mode: str = REQUIRED_SAFE_ZONE_MODE,
) -> Rule07CalloutCard:
    return Rule07CalloutCard(
        card_id=card_id,
        headline=headline,
        duration_sec=duration_sec,
        safe_zone_mode=safe_zone_mode,
        anchor_space="STAGE",
        stage_anchor_x=x,
        stage_anchor_y=y,
    )


def test_two_word_headline_requires_1_6_seconds() -> None:
    assert min_hold_duration_sec(2) == 1.6
    ok = card_2k("c1", "back door", 1.6)
    assert not validate_callout_card(ok)


def test_two_word_headline_1_2_second_remainder_fails() -> None:
    short = card_2k("c2", "kitchen light", 1.2)
    violations = validate_callout_card(short)
    assert any(v.code == "HOLD_TOO_SHORT" for v in violations)


def test_twelve_words_at_boundary_passes() -> None:
    headline = "one two three four five six seven eight nine ten eleven twelve"
    assert count_words(headline) == MAX_WORD_COUNT
    duration = min_hold_duration_sec(MAX_WORD_COUNT)
    assert duration == 4.6
    ok = card_2k("c12", headline, duration)
    assert not validate_callout_card(ok)


def test_thirteen_words_fails() -> None:
    headline = (
        "one two three four five six seven eight nine ten eleven twelve thirteen"
    )
    violations = validate_callout_card(card_2k("c13", headline, 10.0))
    assert any(v.code == "WORD_COUNT_EXCEEDED" for v in violations)


def test_safe_zone_mode_must_be_css_contained() -> None:
    bad = card_2k("c4", "north wing", 1.6, safe_zone_mode="PIXEL_SIM")
    violations = validate_callout_card(bad)
    assert any(v.code == "SAFE_ZONE_MODE" for v in violations)


def test_still_2k_requires_explicit_anchor_coordinates() -> None:
    missing = Rule07CalloutCard(
        card_id="c5",
        headline="entry hall",
        duration_sec=1.6,
        safe_zone_mode=REQUIRED_SAFE_ZONE_MODE,
        anchor_space="STILL_2K",
        anchor_x_px=None,
        anchor_y_px=120,
    )
    violations = validate_callout_card(missing)
    assert any(v.code == "MISSING_ANCHOR_COORDS" for v in violations)


def test_stage_requires_explicit_stage_anchor_coordinates() -> None:
    missing = Rule07CalloutCard(
        card_id="c6",
        headline="act two",
        duration_sec=1.6,
        safe_zone_mode=REQUIRED_SAFE_ZONE_MODE,
        anchor_space="STAGE",
        stage_anchor_x=400.0,
        stage_anchor_y=None,
    )
    violations = validate_callout_card(missing)
    assert any(v.code == "MISSING_ANCHOR_COORDS" for v in violations)


def test_stage_card_passes_with_explicit_coords() -> None:
    ok = card_stage("s1", "west stairwell", 1.6, x=180.0, y=120.0)
    assert not validate_callout_card(ok)


def test_validate_rule_07_aggregates_multiple_cards() -> None:
    cards = [
        card_2k("good", "side gate", 1.6),
        card_2k("bad", "too short", 0.5),
    ]
    result = validate_rule_07(cards)
    assert not result.ok
    assert len(result.violations) == 1
    assert result.violations[0].card_id == "bad"


def test_rule_07_module_avoids_pixel_text_wrap_simulation() -> None:
    tree = ast.parse(RULE_SOURCE.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
    assert not (_BANNED_TERMS & names), "RULE_07 must not simulate pixel text wrapping"