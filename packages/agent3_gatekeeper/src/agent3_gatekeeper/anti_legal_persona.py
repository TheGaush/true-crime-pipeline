"""Anti-AI-legal-persona filter for documentary narration scripts.

Strips unattributed legal advice and interpretive counsel, rewriting to objective
procedural reporting (for example ``the prosecutor charged`` or ``the court held``).
Verbatim judicial language is permitted strictly inside explicit attribution tags:

``[attribution source="court_ruling"]verbatim quote[/attribution]``

Optional locator: ``[attribution source="court_ruling" locator="docket:123"]``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SegmentKind = Literal["plain", "attribution"]
ViolationAction = Literal["rewritten", "rejected"]

ATTRIBUTION_TAG_RE = re.compile(
    r"\[attribution\s+source=\"(?P<source>[^\"]+)\""
    r"(?:\s+locator=\"(?P<locator>[^\"]*)\")?\s*\]"
    r"(?P<body>.*?)"
    r"\[/attribution\]",
    re.DOTALL | re.IGNORECASE,
)

_UNATTRIBUTED_JUDICIAL_QUOTE_RE = re.compile(
    r"\"(?P<quote>[^\"]{8,}?\b(?:held that|we hold|it is ordered|"
    r"the court finds|defendant shall|plaintiff shall)\b[^\"]*?)\"",
    re.IGNORECASE,
)

_REWRITE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\byou\s+should\s+plead\s+(?:guilty|not\s+guilty|no\s+contest)\b",
            re.IGNORECASE,
        ),
        "court records reflect that the defendant entered a plea",
    ),
    (
        re.compile(
            r"\byou\s+should\s+(?:hire|retain|contact)\s+(?:an?\s+)?"
            r"(?:lawyer|attorney|counsel)\b",
            re.IGNORECASE,
        ),
        "the prosecution filed charges according to court records",
    ),
    (
        re.compile(
            r"\bthis\s+means\s+(?:the\s+)?defendant\s+is\s+innocent\b",
            re.IGNORECASE,
        ),
        "the disposition records describe an acquittal",
    ),
    (
        re.compile(
            r"\bthis\s+means\s+(?:the\s+)?defendant\s+is\s+guilty\b",
            re.IGNORECASE,
        ),
        "the disposition records describe a conviction",
    ),
    (
        re.compile(r"\bthis\s+means\s+(?:the\s+)?defendant\s+is\s+not\s+guilty\b", re.IGNORECASE),
        "the disposition records describe an acquittal",
    ),
    (
        re.compile(
            r"\b(?:the\s+)?defendant\s+is\s+clearly\s+innocent\b",
            re.IGNORECASE,
        ),
        "the court entered an acquittal according to the record",
    ),
    (
        re.compile(
            r"\b(?:the\s+)?defendant\s+is\s+clearly\s+guilty\b",
            re.IGNORECASE,
        ),
        "the court entered a conviction according to the record",
    ),
    (
        re.compile(r"\bconsult\s+(?:an?\s+)?(?:lawyer|attorney|counsel)\b", re.IGNORECASE),
        "court filings describe procedural steps in the case",
    ),
    (
        re.compile(r"\blegal\s+advice\b", re.IGNORECASE),
        "objective procedural reporting",
    ),
    (
        re.compile(
            r"\b(?:i|we)\s+recommend\s+(?:that\s+)?you\b",
            re.IGNORECASE,
        ),
        "the record describes steps taken in the proceeding",
    ),
    (
        re.compile(r"\byou\s+should\s+\w+(?:\s+\w+){0,4}\b", re.IGNORECASE),
        "the record describes procedural steps taken in the case",
    ),
    (
        re.compile(r"\bproving\s+(?:guilt|innocence)\b", re.IGNORECASE),
        "the record documents the procedural posture of the case",
    ),
    (
        re.compile(r"\bthey\s+(?:are|were)\s+(?:guilty|innocent)\b", re.IGNORECASE),
        "the disposition records describe the court's outcome",
    ),
)

_BLOCKING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\byou\s+should\b", re.IGNORECASE),
    re.compile(r"\bconsult\s+(?:an?\s+)?(?:lawyer|attorney|counsel)\b", re.IGNORECASE),
    re.compile(r"\blegal\s+advice\b", re.IGNORECASE),
    re.compile(r"\bthis\s+means\s+(?:the\s+)?defendant\s+is\b", re.IGNORECASE),
    re.compile(r"\b(?:they|he|she)\s+(?:are|were)\s+(?:guilty|innocent)\b", re.IGNORECASE),
    re.compile(r"\bproving\s+(?:guilt|innocence)\b", re.IGNORECASE),
    re.compile(r"\b(?:i|we)\s+recommend\b", re.IGNORECASE),
    re.compile(
        r"\bviewers\s+should\s+(?:know|understand|hire|consult)\b",
        re.IGNORECASE,
    ),
)


@dataclass(frozen=True, slots=True)
class AntiLegalViolation:
    rule_id: str
    excerpt: str
    action: ViolationAction


@dataclass(frozen=True, slots=True)
class AntiLegalPersonaResult:
    """Outcome of the anti-legal-persona filter on one script segment or beat."""

    passed: bool
    text: str
    violations: tuple[AntiLegalViolation, ...]
    rewrite_count: int

    @property
    def anti_legal_persona_passed(self) -> bool:
        return self.passed


def _partition_segments(text: str) -> list[tuple[SegmentKind, str]]:
    segments: list[tuple[SegmentKind, str]] = []
    cursor = 0
    for match in ATTRIBUTION_TAG_RE.finditer(text):
        if match.start() > cursor:
            segments.append(("plain", text[cursor : match.start()]))
        segments.append(("attribution", match.group(0)))
        cursor = match.end()
    if cursor < len(text):
        segments.append(("plain", text[cursor:]))
    if not segments:
        segments.append(("plain", text))
    return segments


def _rewrite_plain_segment(segment: str) -> tuple[str, list[AntiLegalViolation]]:
    violations: list[AntiLegalViolation] = []
    updated = segment

    for pattern, replacement in _REWRITE_RULES:
        while pattern.search(updated):
            match = pattern.search(updated)
            assert match is not None
            excerpt = match.group(0)
            violations.append(
                AntiLegalViolation(
                    rule_id=pattern.pattern,
                    excerpt=excerpt,
                    action="rewritten",
                )
            )
            updated = pattern.sub(replacement, updated, count=1)

    while True:
        match = _UNATTRIBUTED_JUDICIAL_QUOTE_RE.search(updated)
        if not match:
            break
        quote_body = match.group("quote").strip()
        procedural = f"the court held that the record states: {quote_body}"
        violations.append(
            AntiLegalViolation(
                rule_id="unattributed_judicial_quote",
                excerpt=match.group(0),
                action="rewritten",
            )
        )
        updated = updated[: match.start()] + procedural + updated[match.end() :]

    return updated, violations


def _blocking_violations_in_plain(segment: str) -> list[AntiLegalViolation]:
    hits: list[AntiLegalViolation] = []
    for pattern in _BLOCKING_PATTERNS:
        for match in pattern.finditer(segment):
            hits.append(
                AntiLegalViolation(
                    rule_id=pattern.pattern,
                    excerpt=match.group(0),
                    action="rejected",
                )
            )
    return hits


def filter_anti_legal_persona(text: str) -> AntiLegalPersonaResult:
    """Rewrite or reject unattributed legal advice; leave attributed quotes intact."""
    all_violations: list[AntiLegalViolation] = []
    rewrite_count = 0
    output_parts: list[str] = []

    for kind, segment in _partition_segments(text):
        if kind == "attribution":
            output_parts.append(segment)
            continue

        rewritten, rewrites = _rewrite_plain_segment(segment)
        rewrite_count += len(rewrites)
        all_violations.extend(rewrites)

        blockers = _blocking_violations_in_plain(rewritten)
        all_violations.extend(blockers)
        output_parts.append(rewritten)

    joined = "".join(output_parts)
    passed = not any(v.action == "rejected" for v in all_violations)

    return AntiLegalPersonaResult(
        passed=passed,
        text=joined,
        violations=tuple(all_violations),
        rewrite_count=rewrite_count,
    )


def contains_legal_advice_persona(text: str) -> bool:
    """Return True when ``text`` still contains blocking legal-advice phrasing."""
    for kind, segment in _partition_segments(text):
        if kind == "attribution":
            continue
        if _blocking_violations_in_plain(segment):
            return True
    return False