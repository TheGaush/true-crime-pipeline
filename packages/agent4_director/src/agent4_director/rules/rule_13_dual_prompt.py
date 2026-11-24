"""RULE_13: dual ``prompt_v1`` + environmental ``prompt_v2_safe`` for hero Flow jobs."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from collections.abc import Iterable, Sequence
from typing import Literal

RULE_ID = "RULE_13"

FLOW_HERO_ENGINE = "FLOW_HERO_VIDEO"

VideoPromptMode = Literal["TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]

_RETIRED_PROMPT_MODES = frozenset({"FRAMES_MOTION_ONLY", "VEO_3_1_LITE"})

_APPEARANCE_NOUNS = frozenset(
    {
        "hooded",
        "detective",
        "charcoal",
        "coat",
        "fedora",
        "jacket",
        "sweater",
        "uniform",
        "suit",
        "beard",
        "ponytail",
    }
)

_CINEMATOGRAPHY_BIGRAMS = (
    "tracking shot",
    "static shot",
    "dolly shot",
    "wide shot",
    "medium shot",
    "panning shot",
    "establishing shot",
    "side tracking shot",
)

_VIOLENCE_TOKENS = frozenset(
    {
        "gun",
        "shoot",
        "shot",
        "minor",
        "victim",
        "suspect",
        "murder",
        "kill",
        "stab",
    }
)

_CONFRONTATION_TOKENS = frozenset(
    {
        "struggle",
        "struggles",
        "struggling",
        "chase",
        "chasing",
        "chased",
        "fight",
        "fighting",
        "fought",
        "confront",
        "confrontation",
        "confronting",
        "attack",
        "attacking",
        "assault",
        "wrestle",
        "wrestling",
        "grapple",
        "grappling",
        "pursue",
        "pursuing",
        "pursuit",
        "flee",
        "fleeing",
        "fled",
        "ambush",
        "tackle",
        "tackling",
        "punch",
        "punching",
        "kick",
        "kicking",
        "choke",
        "choking",
        "combat",
        "battle",
        "hostage",
        "kidnap",
        "kidnapping",
        "menace",
        "threaten",
        "threatening",
        "overpower",
    }
)

_PERSON_TOKENS = frozenset(
    {
        "person",
        "people",
        "man",
        "men",
        "woman",
        "women",
        "child",
        "children",
        "teen",
        "crowd",
        "pedestrian",
        "officer",
        "detective",
        "suspect",
        "victim",
        "intruder",
        "attacker",
        "perpetrator",
        "witness",
        "suspects",
        "victims",
    }
)

_ENVIRONMENTAL_MOTION_HINTS = frozenset(
    {
        "flashlight",
        "beam",
        "rain",
        "reflection",
        "reflections",
        "door",
        "swing",
        "swinging",
        "drip",
        "dripping",
        "fog",
        "mist",
        "wind",
        "leaf",
        "leaves",
        "curtain",
        "ripple",
        "puddle",
        "pendulum",
        "sway",
        "swaying",
        "flicker",
        "flickering",
        "dust",
        "empty",
        "alley",
        "room",
        "steps",
        "courthouse",
        "corridor",
        "hallway",
        "window",
        "shadow",
        "shadows",
        "neon",
        "streetlight",
        "camera",
        "tracking",
        "dolly",
        "pan",
        "panning",
        "monochrome",
    }
)

_WORD_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class Rule13HeroScene:
    scene_id: str
    visual_engine: str
    prompt_mode: VideoPromptMode
    prompt_v1: str | None = None
    prompt_v2_safe: str | None = None
    duration_bucket_sec: int = 8


@dataclass(frozen=True, slots=True)
class Rule13Violation:
    code: str
    message: str
    scene_id: str | None = None
    rule_id: str = RULE_ID
    field: str | None = None


@dataclass(slots=True)
class Rule13Result:
    violations: list[Rule13Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def _tokenize(text: str) -> list[str]:
    return [match.group(0).lower() for match in _WORD_RE.finditer(text)]


def _mask_cinematography_bigrams(text: str) -> str:
    masked = text.lower()
    for bigram in _CINEMATOGRAPHY_BIGRAMS:
        masked = masked.replace(bigram, " " * len(bigram))
    return masked


def _find_token(tokens: Iterable[str], forbidden: frozenset[str]) -> str | None:
    for token in tokens:
        if token in forbidden:
            return token
    return None


def _rule_11_violations(
    prompt: str,
    prompt_mode: VideoPromptMode,
    *,
    scene_id: str,
    field_name: str,
) -> list[Rule13Violation]:
    violations: list[Rule13Violation] = []
    if not prompt or not prompt.strip():
        violations.append(
            Rule13Violation(
                code="PROMPT_EMPTY",
                scene_id=scene_id,
                field=field_name,
                message=f"{field_name} must be non-empty for hero scene {scene_id}",
            )
        )
        return violations

    try:
        from agent4_director.rules.rule_11_prompt_compress import (  # noqa: PLC0415
            validate_rule_11,
        )

        delegated = validate_rule_11(prompt, prompt_mode)
        for item in getattr(delegated, "violations", delegated):
            code = getattr(item, "code", "RULE_11_DELEGATE")
            message = getattr(item, "message", str(item))
            violations.append(
                Rule13Violation(
                    code=code,
                    scene_id=scene_id,
                    field=field_name,
                    message=f"{field_name} {message}",
                )
            )
        return violations
    except ImportError:
        pass

    words = _tokenize(prompt)
    if prompt_mode in ("FIRST_FRAME", "FIRST_AND_LAST_FRAME"):
        hit = _find_token(words, _APPEARANCE_NOUNS)
        if hit:
            violations.append(
                Rule13Violation(
                    code="APPEARANCE_NOUN_FORBIDDEN",
                    scene_id=scene_id,
                    field=field_name,
                    message=(
                        f"{field_name} must not contain appearance noun '{hit}' "
                        f"when prompt_mode is {prompt_mode}"
                    ),
                )
            )
    return violations


def _rule_12_violations(
    prompt: str,
    prompt_mode: VideoPromptMode,
    *,
    scene_id: str,
    field_name: str,
) -> list[Rule13Violation]:
    try:
        from agent4_director.rules.rule_12_anonymizer import validate_rule_12  # noqa: PLC0415

        delegated = validate_rule_12(prompt, prompt_mode)
        for item in getattr(delegated, "violations", delegated):
            code = getattr(item, "code", "RULE_12_DELEGATE")
            message = getattr(item, "message", str(item))
            violations.append(
                Rule13Violation(
                    code=code,
                    scene_id=scene_id,
                    field=field_name,
                    message=f"{field_name} {message}",
                )
            )
        return violations
    except ImportError:
        pass

    violations: list[Rule13Violation] = []
    scrubbed = _mask_cinematography_bigrams(prompt)
    tokens = _tokenize(scrubbed)
    hit = _find_token(tokens, _VIOLENCE_TOKENS)
    if hit:
        violations.append(
            Rule13Violation(
                code="ANONYMIZER_VIOLATION",
                scene_id=scene_id,
                field=field_name,
                message=f"{field_name} triggers RULE_12 token '{hit}'",
            )
        )
    return violations


def _prompt_mode_violations(
    prompt_mode: VideoPromptMode,
    *,
    scene_id: str,
    duration_bucket_sec: int,
) -> list[Rule13Violation]:
    violations: list[Rule13Violation] = []
    if prompt_mode in _RETIRED_PROMPT_MODES:  # type: ignore[comparison-overlap]
        violations.append(
            Rule13Violation(
                code="RETIRED_PROMPT_MODE",
                scene_id=scene_id,
                message=f"prompt_mode {prompt_mode} is retired (F-04)",
            )
        )
    if prompt_mode == "FIRST_AND_LAST_FRAME" and duration_bucket_sec > 10:
        violations.append(
            Rule13Violation(
                code="DURATION_MODE_MISMATCH",
                scene_id=scene_id,
                message=(
                    f"FIRST_AND_LAST_FRAME hero clip {scene_id} duration "
                    f"{duration_bucket_sec}s exceeds 10s cap"
                ),
            )
        )
    return violations


def _v2_environmental_violations(
    prompt_v2_safe: str,
    *,
    scene_id: str,
) -> list[Rule13Violation]:
    violations: list[Rule13Violation] = []
    lowered = prompt_v2_safe.lower()
    tokens = _tokenize(lowered)

    confrontation = _find_token(tokens, _CONFRONTATION_TOKENS)
    if confrontation:
        violations.append(
            Rule13Violation(
                code="V2_CONFRONTATION_WORD",
                scene_id=scene_id,
                field="prompt_v2_safe",
                message=(
                    f"prompt_v2_safe must not contain confrontation token "
                    f"'{confrontation}' for {scene_id}"
                ),
            )
        )

    person = _find_token(tokens, _PERSON_TOKENS)
    if person:
        violations.append(
            Rule13Violation(
                code="V2_PERSON_WORD",
                scene_id=scene_id,
                field="prompt_v2_safe",
                message=(
                    f"prompt_v2_safe must stay environmental; found person token "
                    f"'{person}' for {scene_id}"
                ),
            )
        )

    if not any(hint in lowered for hint in _ENVIRONMENTAL_MOTION_HINTS):
        violations.append(
            Rule13Violation(
                code="V2_NOT_ENVIRONMENTAL",
                scene_id=scene_id,
                field="prompt_v2_safe",
                message=(
                    f"prompt_v2_safe must describe environmental motion only "
                    f"(flashlight beam, rain, swinging door, etc.) for {scene_id}"
                ),
            )
        )
    return violations


_CONFRONTATION_ROOTS = frozenset(
    {
        "struggle",
        "chase",
        "fight",
        "confront",
        "attack",
        "assault",
        "wrestle",
        "grapple",
        "pursu",
        "flee",
        "ambush",
        "tackle",
        "punch",
        "kick",
        "choke",
        "combat",
        "battle",
        "hostage",
        "kidnap",
        "menace",
        "threaten",
        "overpower",
    }
)


def _confrontation_roots_in(text: str) -> set[str]:
    lowered = text.lower()
    return {root for root in _CONFRONTATION_ROOTS if root in lowered}


def _v2_reuses_v1_confrontation(
    prompt_v1: str,
    prompt_v2_safe: str,
    *,
    scene_id: str,
) -> Rule13Violation | None:
    shared_roots = _confrontation_roots_in(prompt_v1) & _confrontation_roots_in(
        prompt_v2_safe
    )
    if shared_roots:
        root = sorted(shared_roots)[0]
        return Rule13Violation(
            code="V2_REUSES_V1_CONFRONTATION",
            scene_id=scene_id,
            field="prompt_v2_safe",
            message=(
                f"prompt_v2_safe must not reuse confrontation stem '{root}' "
                f"from prompt_v1 on {scene_id}"
            ),
        )
    return None


def validate_rule_13(scenes: Sequence[Rule13HeroScene]) -> Rule13Result:
    """Validate dual hero prompts (pre-compiler / manifest linter)."""
    violations: list[Rule13Violation] = []
    for scene in scenes:
        if scene.visual_engine != FLOW_HERO_ENGINE:
            continue

        if scene.prompt_v1 is None or not str(scene.prompt_v1).strip():
            violations.append(
                Rule13Violation(
                    code="MISSING_PROMPT_V1",
                    scene_id=scene.scene_id,
                    field="prompt_v1",
                    message=f"hero scene {scene.scene_id} requires prompt_v1",
                )
            )
        if scene.prompt_v2_safe is None or not str(scene.prompt_v2_safe).strip():
            violations.append(
                Rule13Violation(
                    code="MISSING_PROMPT_V2_SAFE",
                    scene_id=scene.scene_id,
                    field="prompt_v2_safe",
                    message=f"hero scene {scene.scene_id} requires prompt_v2_safe",
                )
            )
        if (
            scene.prompt_v1 is None
            or not str(scene.prompt_v1).strip()
            or scene.prompt_v2_safe is None
            or not str(scene.prompt_v2_safe).strip()
        ):
            continue

        prompt_v1 = str(scene.prompt_v1).strip()
        prompt_v2_safe = str(scene.prompt_v2_safe).strip()

        violations.extend(
            _prompt_mode_violations(
                scene.prompt_mode,
                scene_id=scene.scene_id,
                duration_bucket_sec=scene.duration_bucket_sec,
            )
        )
        violations.extend(
            _rule_11_violations(
                prompt_v1,
                scene.prompt_mode,
                scene_id=scene.scene_id,
                field_name="prompt_v1",
            )
        )
        violations.extend(
            _rule_11_violations(
                prompt_v2_safe,
                scene.prompt_mode,
                scene_id=scene.scene_id,
                field_name="prompt_v2_safe",
            )
        )
        violations.extend(
            _rule_12_violations(
                prompt_v1,
                scene.prompt_mode,
                scene_id=scene.scene_id,
                field_name="prompt_v1",
            )
        )
        violations.extend(
            _rule_12_violations(
                prompt_v2_safe,
                scene.prompt_mode,
                scene_id=scene.scene_id,
                field_name="prompt_v2_safe",
            )
        )
        violations.extend(
            _v2_environmental_violations(prompt_v2_safe, scene_id=scene.scene_id)
        )
        reuse = _v2_reuses_v1_confrontation(
            prompt_v1, prompt_v2_safe, scene_id=scene.scene_id
        )
        if reuse is not None:
            violations.append(reuse)

    return Rule13Result(violations=violations)