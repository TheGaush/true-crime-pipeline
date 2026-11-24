"""RULE_11: split prompt_mode compressor for gemini-omni-1.2-flash motion prompts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

RULE_ID: Final = "RULE_11"

MOTION_WORD_MIN = 15
MOTION_WORD_MAX = 30

DURATION_MS_MIN = 3_000
DURATION_MS_TEXT_OR_FIRST_MAX = 15_000
DURATION_MS_FIRST_AND_LAST_MAX = 10_000

CANONICAL_PROMPT_MODES = frozenset(
    {"TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"}
)
FRAME_MOTION_MODES = frozenset({"FIRST_FRAME", "FIRST_AND_LAST_FRAME"})
RETIRED_PROMPT_MODES = frozenset({"FRAMES_MOTION_ONLY", "VEO_3_1_LITE"})

APPEARANCE_BANNED_WORDS: Final[tuple[str, ...]] = (
    "hooded",
    "detective",
    "charcoal",
    "coat",
    "fedora",
)

_RETIRED_PROMPT_SUBSTRINGS: Final[tuple[str, ...]] = (
    "FRAMES_MOTION_ONLY",
    "VEO_3_1_LITE",
    "Veo 3.1 Lite",
)

_WORD_RE = re.compile(r"\b[\w']+\b", re.UNICODE)
_APPEARANCE_WORD_RE = re.compile(
    r"\b(" + "|".join(re.escape(word) for word in APPEARANCE_BANNED_WORDS) + r")\b",
    re.IGNORECASE,
)
_STYLIZED_SUBJECT_PREFIX_RE = re.compile(
    r"^\s*(?:\d+d\s+ink\s+figure|ink\s+figure|\d+d\s+figure)\b",
    re.IGNORECASE,
)
_NO_WORD_RE = re.compile(r"\bno\b", re.IGNORECASE)
_DONT_SHOW_RE = re.compile(r"don'?t\s+show", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Rule11Scene:
    scene_id: str
    prompt_mode: str
    visual_prompt: str
    duration_ms: int


@dataclass(frozen=True, slots=True)
class Rule11Violation:
    code: str
    message: str
    scene_id: str | None = None
    rule_id: str = RULE_ID


@dataclass(slots=True)
class Rule11Result:
    violations: list[Rule11Violation] = field(default_factory=list)
    compressed_prompts: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.violations


def count_motion_words(prompt: str) -> int:
    """Return word count for motion-prompt length enforcement."""
    return len(_WORD_RE.findall(prompt.strip()))


def contains_negative_keyword_ban(prompt: str) -> bool:
    """True when prompt includes banned negative wording (whole-word 'no' or 'don't show')."""
    lowered = prompt.lower()
    if _DONT_SHOW_RE.search(lowered):
        return True
    return bool(_NO_WORD_RE.search(prompt))


def _duration_bounds_ms(prompt_mode: str) -> tuple[int, int] | None:
    if prompt_mode in {"TEXT_TO_VIDEO", "FIRST_FRAME"}:
        return DURATION_MS_MIN, DURATION_MS_TEXT_OR_FIRST_MAX
    if prompt_mode == "FIRST_AND_LAST_FRAME":
        return DURATION_MS_MIN, DURATION_MS_FIRST_AND_LAST_MAX
    return None


def compress_motion_prompt(visual_prompt: str, prompt_mode: str) -> str:
    """Strip appearance descriptors for frame-keyed modes; pass through TEXT_TO_VIDEO."""
    text = " ".join(visual_prompt.split())
    if prompt_mode not in FRAME_MOTION_MODES:
        return text

    stripped = _APPEARANCE_WORD_RE.sub("", text)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip(" ,")
    if not stripped:
        return stripped

    match = _STYLIZED_SUBJECT_PREFIX_RE.match(stripped)
    if match:
        remainder = stripped[match.end() :].lstrip(" ,")
        stripped = f"Figure {remainder}".strip()

    return stripped.strip()


def _contains_retired_contract_drift(value: str) -> str | None:
    for token in _RETIRED_PROMPT_SUBSTRINGS:
        if token.lower() in value.lower():
            return token
    return None


def validate_rule_11(scenes: list[Rule11Scene]) -> Rule11Result:
    """Validate and compress hero motion prompts under RULE_11."""
    result = Rule11Result()

    for scene in scenes:
        sid = scene.scene_id
        mode = scene.prompt_mode.strip()
        prompt = scene.visual_prompt.strip()

        retired_mode = _contains_retired_contract_drift(mode)
        if mode in RETIRED_PROMPT_MODES or retired_mode:
            token = retired_mode or mode
            result.violations.append(
                Rule11Violation(
                    code="RETIRED_PROMPT_MODE",
                    message=f"retired prompt_mode contract drift: {token!r}",
                    scene_id=sid,
                )
            )
            continue

        if mode not in CANONICAL_PROMPT_MODES:
            result.violations.append(
                Rule11Violation(
                    code="UNKNOWN_PROMPT_MODE",
                    message=f"unsupported prompt_mode {mode!r}",
                    scene_id=sid,
                )
            )
            continue

        retired_prompt = _contains_retired_contract_drift(prompt)
        if retired_prompt:
            result.violations.append(
                Rule11Violation(
                    code="RETIRED_PROMPT_TEXT",
                    message=f"visual_prompt references retired contract {retired_prompt!r}",
                    scene_id=sid,
                )
            )

        bounds = _duration_bounds_ms(mode)
        if bounds is not None:
            lo, hi = bounds
            if not (lo <= scene.duration_ms <= hi):
                sec = scene.duration_ms / 1000.0
                result.violations.append(
                    Rule11Violation(
                        code="DURATION_OUT_OF_RANGE",
                        message=(
                            f"{mode} duration {sec:.3f}s ({scene.duration_ms} ms) "
                            f"outside {lo / 1000:.0f}s–{hi / 1000:.0f}s"
                        ),
                        scene_id=sid,
                    )
                )

        compressed = compress_motion_prompt(prompt, mode)
        result.compressed_prompts[sid] = compressed
        word_count = count_motion_words(compressed)

        if word_count < MOTION_WORD_MIN or word_count > MOTION_WORD_MAX:
            result.violations.append(
                Rule11Violation(
                    code="MOTION_WORD_COUNT",
                    message=(
                        f"motion prompt must be {MOTION_WORD_MIN}–{MOTION_WORD_MAX} words "
                        f"(got {word_count})"
                    ),
                    scene_id=sid,
                )
            )

        if contains_negative_keyword_ban(compressed):
            result.violations.append(
                Rule11Violation(
                    code="NEGATIVE_KEYWORD_BAN",
                    message='motion prompt must not contain "no" or "don\'t show"',
                    scene_id=sid,
                )
            )

        if mode in FRAME_MOTION_MODES:
            if _APPEARANCE_WORD_RE.search(compressed):
                result.violations.append(
                    Rule11Violation(
                        code="APPEARANCE_DESCRIPTOR",
                        message=(
                            "frame-keyed prompts must not retain appearance words "
                            f"{APPEARANCE_BANNED_WORDS}"
                        ),
                        scene_id=sid,
                    )
                )
            if prompt != compressed and _APPEARANCE_WORD_RE.search(prompt):
                # Informational pass: compressor removed appearance drift.
                pass

    return result