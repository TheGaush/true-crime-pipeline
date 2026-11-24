"""RULE_07: 12-Word Glance hold time and CSS-delegated safe-zone contract checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

RULE_ID = "RULE_07"

MAX_WORD_COUNT = 12
BASE_HOLD_SEC = 1.0
SEC_PER_WORD = 0.3
REQUIRED_SAFE_ZONE_MODE = "CSS_CONTAINED"

AnchorSpace = Literal["STILL_2K", "STAGE"]


@dataclass(frozen=True, slots=True)
class Rule07CalloutCard:
    """Location / timestamp / action glance card validated under RULE_07."""

    card_id: str
    headline: str
    duration_sec: float
    safe_zone_mode: str
    anchor_space: AnchorSpace
    anchor_x_px: int | None = None
    anchor_y_px: int | None = None
    stage_anchor_x: float | None = None
    stage_anchor_y: float | None = None


@dataclass(frozen=True, slots=True)
class Rule07Violation:
    code: str
    message: str
    card_id: str | None = None
    rule_id: str = RULE_ID


@dataclass(slots=True)
class Rule07Result:
    violations: list[Rule07Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def count_words(text: str) -> int:
    """Count whitespace-delimited tokens in callout headline text."""
    return len(text.split())


def min_hold_duration_sec(word_count: int) -> float:
    """Minimum on-screen hold: 1.0s base + 0.3s per word."""
    return BASE_HOLD_SEC + SEC_PER_WORD * word_count


def _check_word_count(card: Rule07CalloutCard, words: int) -> Rule07Violation | None:
    if words > MAX_WORD_COUNT:
        return Rule07Violation(
            code="WORD_COUNT_EXCEEDED",
            card_id=card.card_id,
            message=(
                f"card {card.card_id} has {words} words (limit {MAX_WORD_COUNT})"
            ),
        )
    return None


def _check_hold(card: Rule07CalloutCard, words: int) -> Rule07Violation | None:
    minimum = min_hold_duration_sec(words)
    if card.duration_sec + 1e-9 < minimum:
        return Rule07Violation(
            code="HOLD_TOO_SHORT",
            card_id=card.card_id,
            message=(
                f"card {card.card_id} duration {card.duration_sec}s is below "
                f"{minimum}s minimum for {words} words"
            ),
        )
    return None


def _check_safe_zone_mode(card: Rule07CalloutCard) -> Rule07Violation | None:
    if card.safe_zone_mode != REQUIRED_SAFE_ZONE_MODE:
        return Rule07Violation(
            code="SAFE_ZONE_MODE",
            card_id=card.card_id,
            message=(
                f"card {card.card_id} safe_zone_mode must be "
                f"{REQUIRED_SAFE_ZONE_MODE!r}, got {card.safe_zone_mode!r}"
            ),
        )
    return None


def _check_anchor_coords(card: Rule07CalloutCard) -> Rule07Violation | None:
    if card.anchor_space == "STILL_2K":
        if card.anchor_x_px is None or card.anchor_y_px is None:
            return Rule07Violation(
                code="MISSING_ANCHOR_COORDS",
                card_id=card.card_id,
                message=(
                    f"card {card.card_id} requires explicit 2K anchor_x_px and "
                    "anchor_y_px coordinates"
                ),
            )
        if card.anchor_x_px < 0 or card.anchor_y_px < 0:
            return Rule07Violation(
                code="INVALID_ANCHOR_COORDS",
                card_id=card.card_id,
                message=(
                    f"card {card.card_id} 2K anchor coordinates must be non-negative"
                ),
            )
        return None

    if card.stage_anchor_x is None or card.stage_anchor_y is None:
        return Rule07Violation(
            code="MISSING_ANCHOR_COORDS",
            card_id=card.card_id,
            message=(
                f"card {card.card_id} requires explicit stage_anchor_x and "
                "stage_anchor_y coordinates"
            ),
        )
    if card.stage_anchor_x < 0 or card.stage_anchor_y < 0:
        return Rule07Violation(
            code="INVALID_ANCHOR_COORDS",
            card_id=card.card_id,
            message=(
                f"card {card.card_id} stage anchor coordinates must be non-negative"
            ),
        )
    return None


def validate_callout_card(card: Rule07CalloutCard) -> list[Rule07Violation]:
    """Validate a single glance card under RULE_07 (no pixel text-wrap simulation)."""
    violations: list[Rule07Violation] = []
    words = count_words(card.headline)

    for check in (
        _check_word_count(card, words),
        _check_hold(card, words),
        _check_safe_zone_mode(card),
        _check_anchor_coords(card),
    ):
        if check is not None:
            violations.append(check)
    return violations


def validate_rule_07(cards: list[Rule07CalloutCard]) -> Rule07Result:
    """Run RULE_07 on all callout glance cards in a manifest slice."""
    violations: list[Rule07Violation] = []
    for card in cards:
        violations.extend(validate_callout_card(card))
    return Rule07Result(violations=violations)