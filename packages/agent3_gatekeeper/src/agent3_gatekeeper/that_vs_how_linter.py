"""Clinical \"that\" phrasing rewriter for documentary narration (that-vs-how-linter@1).

Normalizes script text with NFKC, rewrites mechanism or suffering \"how\" wording
into attributed forensic \"that\" reporting, then enforces a zero-tolerance scan for
blocked tokens. No network and no LLM calls.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final

# Category tags only — no graphic instructional detail in comments.
_MECHANISM: Final[str] = "mechanism"
_SUFFERING: Final[str] = "suffering"
_HOW_FRAMING: Final[str] = "how_framing"

_BANNED_BY_CATEGORY: dict[str, frozenset[str]] = {
    _MECHANISM: frozenset(
        {
            "stabbed",
            "stabbing",
            "stab",
            "sliced",
            "slashed",
            "strangled",
            "suffocated",
            "decapitated",
            "dismembered",
            "mutilated",
            "eviscerated",
            "impaled",
            "garroted",
            "lacerated",
            "disemboweled",
            "hacked",
            "gouged",
            "bludgeoned",
            "asphyxiated",
            "throttled",
            "skinned",
            "severed",
            "amputated",
            "punctured",
            "tortured",
        }
    ),
    _SUFFERING: frozenset(
        {
            "agonizing",
            "writhing",
            "convulsing",
            "hemorrhaging",
            "gushing",
            "spurting",
            "spasming",
            "screaming",
            "howling",
            "wailing",
            "shrieking",
            "bleeding",
            "oozing",
            "drowning",
            "gasping",
            "choking",
        }
    ),
    _HOW_FRAMING: frozenset(
        {
            "step-by-step",
            "play-by-play",
            "blow-by-blow",
        }
    ),
}

BANNED_TOKENS: frozenset[str] = frozenset().union(*_BANNED_BY_CATEGORY.values())

_CLINICAL_DEFAULT = (
    "The medical examiner reported that the injury was fatal."
)
_CLINICAL_INVESTIGATORS = (
    "Investigators reported that the manner of death was documented in the case file."
)
_CLINICAL_COURT = (
    "Court records indicate that injuries consistent with the charges were documented."
)

_CLINICAL_TEMPLATES: tuple[str, ...] = (
    _CLINICAL_DEFAULT,
    _CLINICAL_INVESTIGATORS,
    _CLINICAL_COURT,
)

_HOW_STYLE_RE: re.Pattern[str] = re.compile(
    r"""
    \bhow\s+(?:he|she|they|the\s+suspect|the\s+defendant)\s+
    (?:killed|murdered|attacked|harmed|injured)\b
    |
    \b(?:he|she|they)\s+first\b.*\b(?:then|before|after)\b
    |
    \bin\s+order\s+to\s+(?:kill|murder|harm|injure)\b
    |
    \bstep\s+by\s+step\b
    """,
    re.IGNORECASE | re.VERBOSE | re.DOTALL,
)

_ATTRIBUTED_THAT_RE: re.Pattern[str] = re.compile(
    r"\b(?:reported|determined|indicated|documented|established|found|concluded)"
    r"\s+that\b",
    re.IGNORECASE,
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

def _token_pattern(token: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in token.split("-")]
    body = r"[-\s]?".join(parts)
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", re.IGNORECASE)


_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = tuple(
    (token, _token_pattern(token))
    for token in sorted(BANNED_TOKENS, key=len, reverse=True)
)


def normalize_nfkc(text: str) -> str:
    """Return NFKC-normalized text for scanning and rewrite decisions."""
    return unicodedata.normalize("NFKC", text)


def normalize_for_scan(text: str) -> str:
    """NFKC plus casefold for zero-tolerance token matching."""
    return normalize_nfkc(text).casefold()


def find_banned_tokens(text: str) -> tuple[str, ...]:
    """Return banned graphic tokens present in ``text`` (NFKC, case-insensitive)."""
    folded = normalize_for_scan(text)
    hits: list[str] = []
    for token, pattern in _TOKEN_PATTERNS:
        if pattern.search(folded):
            hits.append(token)
    return tuple(hits)


def zero_tolerance_scan(text: str) -> tuple[str, ...]:
    """Zero-tolerance post-rewrite scan; any hit fails the linter."""
    return find_banned_tokens(text)


def _is_clinical_that_sentence(sentence: str) -> bool:
    if find_banned_tokens(sentence):
        return False
    if _HOW_STYLE_RE.search(normalize_nfkc(sentence)):
        return False
    return bool(_ATTRIBUTED_THAT_RE.search(sentence))


def _rewrite_sentence(sentence: str, template_index: int) -> str:
    template = _CLINICAL_TEMPLATES[template_index % len(_CLINICAL_TEMPLATES)]
    stripped = sentence.strip()
    if not stripped:
        return sentence
    leading = sentence[: len(sentence) - len(sentence.lstrip())]
    trailing = sentence[len(sentence.rstrip()) :]
    return f"{leading}{template}{trailing}"


def rewrite_sentence(sentence: str, *, template_index: int = 0) -> str:
    """Rewrite one sentence to clinical \"that\" phrasing when required."""
    normalized = normalize_nfkc(sentence)
    if _is_clinical_that_sentence(normalized):
        return sentence
    if not find_banned_tokens(normalized) and not _HOW_STYLE_RE.search(normalized):
        return sentence
    return _rewrite_sentence(sentence, template_index)


@dataclass(frozen=True, slots=True)
class ThatVsHowLintResult:
    """Outcome of linting one script block or sentence."""

    original: str
    rewritten: str
    changed: bool
    residual_violations: tuple[str, ...]
    passed: bool

    @property
    def that_vs_how_passed(self) -> bool:
        return self.passed


def lint_text(text: str) -> ThatVsHowLintResult:
    """NFKC-normalize, rewrite \"how\" wording, then zero-tolerance scan."""
    normalized = normalize_nfkc(text)
    parts = _SENTENCE_SPLIT_RE.split(normalized)
    if not parts:
        parts = [normalized]
    rewritten_parts: list[str] = []
    changed = False
    for index, part in enumerate(parts):
        new_part = rewrite_sentence(part, template_index=index)
        if new_part != part:
            changed = True
        rewritten_parts.append(new_part)
    rewritten = " ".join(rewritten_parts)
    violations = zero_tolerance_scan(rewritten)
    passed = len(violations) == 0
    return ThatVsHowLintResult(
        original=text,
        rewritten=rewritten,
        changed=changed,
        residual_violations=violations,
        passed=passed,
    )