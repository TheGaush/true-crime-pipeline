"""RULE_12 split anonymizer: cinematography bigram whitelist + mode metaphor tables."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

PromptMode = Literal["TEXT_TO_VIDEO", "FIRST_FRAME", "FIRST_AND_LAST_FRAME"]

RULE_12_ID = "RULE_12"

_MASK_PLACEHOLDER = "\x00cam\x00"

CINEMATOGRAPHY_BIGRAM_WHITELIST: tuple[str, ...] = (
    "tracking shot",
    "static shot",
    "dolly shot",
    "wide shot",
    "medium shot",
    "panning shot",
    "establishing shot",
)

# Longer compound phrases masked before the generic bigram list.
_CINEMATOGRAPHY_COMPOUND_PHRASES: tuple[str, ...] = (
    "shooting tracking shot",
    "smooth side tracking shot",
)

_BLOCKED_SAFETY_PATTERN = re.compile(
    r"\b(?:shoot(?:s|ing)?|shot(?:s)?|guns?|minors?)\b",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?", re.IGNORECASE)

_FRAME_FORBIDDEN_APPEARANCE: frozenset[str] = frozenset(
    {
        "hooded",
        "detective",
        "charcoal",
        "coat",
        "fedora",
        "jacket",
        "sweater",
        "blonde",
        "brunette",
        "beard",
        "mustache",
        "mugshot",
        "face",
        "skin",
        "hair",
        "ink",
        "parchment",
        "silhouette",
        "silhouettes",
    }
)

_T2V_FORBIDDEN_APPEARANCE: frozenset[str] = frozenset(
    _FRAME_FORBIDDEN_APPEARANCE
    | {
        "person",
        "people",
        "man",
        "woman",
        "suspect",
        "victim",
        "child",
        "teen",
        "teenager",
    }
)

_TEXT_TO_VIDEO_STYLIZED_MARKERS: frozenset[str] = frozenset(
    {
        "silhouette",
        "silhouettes",
        "stylized",
        "minimalist",
        "stick",
        "figure",
        "2d",
        "atmospheric",
        "abstract",
        "noir",
    }
)

@dataclass(frozen=True)
class Rule12Finding:
    rule_id: str
    message: str
    severity: str = "error"
    blocked_terms: tuple[str, ...] = ()
    prompt_mode: str | None = None


@dataclass
class Rule12Report:
    passed: bool
    findings: list[Rule12Finding] = field(default_factory=list)
    masked_prompt: str = ""


def mask_cinematography_bigrams(text: str) -> str:
    """Replace whitelisted camera bigrams so safety scans skip benign ``shot`` usage."""
    lowered = text.lower()
    for phrase in _CINEMATOGRAPHY_COMPOUND_PHRASES:
        lowered = lowered.replace(phrase, _MASK_PLACEHOLDER)
    for bigram in CINEMATOGRAPHY_BIGRAM_WHITELIST:
        lowered = lowered.replace(bigram, _MASK_PLACEHOLDER)
    return lowered


def find_blocked_safety_terms(text: str) -> tuple[str, ...]:
    """Return blocked shoot/shot/gun/minor tokens after cinematography masking."""
    masked = mask_cinematography_bigrams(text)
    hits = [match.group(0).lower() for match in _BLOCKED_SAFETY_PATTERN.finditer(masked)]
    return tuple(dict.fromkeys(hits))


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _frame_mode_appearance_violations(prompt: str) -> list[str]:
    """FIRST_FRAME / FIRST_AND_LAST_FRAME: forbid appearance/clothing/material nouns."""
    return [tok for tok in _tokens(prompt) if tok in _FRAME_FORBIDDEN_APPEARANCE]


def _text_to_video_metaphor_violations(prompt: str) -> list[str]:
    """TEXT_TO_VIDEO: allow stylized silhouette tags; block raw appearance descriptors."""
    violations: list[str] = []
    for token in _tokens(prompt):
        if token in _T2V_FORBIDDEN_APPEARANCE and token not in _TEXT_TO_VIDEO_STYLIZED_MARKERS:
            violations.append(token)
    return violations


def check_rule_12(prompt: str, prompt_mode: str) -> Rule12Report:
    """Validate prompt against RULE_12 stage-1 safety scrub and stage-2 metaphor tables."""
    findings: list[Rule12Finding] = []
    masked = mask_cinematography_bigrams(prompt)

    blocked = find_blocked_safety_terms(prompt)
    if blocked:
        findings.append(
            Rule12Finding(
                rule_id=RULE_12_ID,
                message=f"blocked safety terms after cinematography mask: {', '.join(blocked)}",
                blocked_terms=blocked,
                prompt_mode=prompt_mode,
            )
        )

    if prompt_mode in ("FIRST_FRAME", "FIRST_AND_LAST_FRAME"):
        appearance_hits = _frame_mode_appearance_violations(prompt)
        if appearance_hits:
            findings.append(
                Rule12Finding(
                    rule_id=RULE_12_ID,
                    message=(
                        "FIRST_FRAME modes allow only motion and camera verbs; "
                        f"found: {', '.join(sorted(set(appearance_hits)))}"
                    ),
                    blocked_terms=tuple(sorted(set(appearance_hits))),
                    prompt_mode=prompt_mode,
                )
            )
    elif prompt_mode == "TEXT_TO_VIDEO":
        metaphor_hits = _text_to_video_metaphor_violations(prompt)
        if metaphor_hits:
            findings.append(
                Rule12Finding(
                    rule_id=RULE_12_ID,
                    message=(
                        "TEXT_TO_VIDEO requires atmospheric stylized silhouette tags; "
                        f"issues: {', '.join(metaphor_hits)}"
                    ),
                    blocked_terms=tuple(metaphor_hits),
                    prompt_mode=prompt_mode,
                )
            )
    else:
        findings.append(
            Rule12Finding(
                rule_id=RULE_12_ID,
                message=f"unsupported prompt_mode {prompt_mode!r}",
                prompt_mode=prompt_mode,
            )
        )

    return Rule12Report(passed=not findings, findings=findings, masked_prompt=masked)


def rule_12_passes(prompt: str, prompt_mode: str) -> bool:
    return check_rule_12(prompt, prompt_mode).passed