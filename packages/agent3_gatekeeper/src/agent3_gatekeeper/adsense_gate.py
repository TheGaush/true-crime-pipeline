"""First-30s AdSense safety gate and hard-blocked topic classifier (Agent 3).

``first_30s_adsense_safe = 1`` only when the episode ``0:00``–``0:30`` window
contains no profanity, weapon terms, or graphic distress tags in opening
narration and in any FOIA slice routed into that cold-open window.

FOIA profanity is checked on the **source** timeline: any entry in
``profanity_intervals_json`` overlapping the slice's ``source_start_ms``–
``source_end_ms`` fails the gate (bleeping alone does not clear AdSense risk).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

EPISODE_INTRO_END_MS = 30_000

_REASON_CLEAN = "intro_adsense_clean"
_REASON_PROFANITY = "profanity_in_intro"
_REASON_WEAPON = "weapon_term_in_intro"
_REASON_DISTRESS = "graphic_distress_in_intro"
_REASON_FOIA_PROFANITY = "foia_profanity_overlaps_intro_slice"

_TOKEN_RE = re.compile(r"[^a-z0-9]+")

_PROFANITY_WORDS: frozenset[str] = frozenset(
    {
        "fuck",
        "fucking",
        "fucked",
        "fucker",
        "shit",
        "shitty",
        "bitch",
        "bastard",
        "asshole",
        "dick",
        "cock",
        "pussy",
        "whore",
        "slut",
        "damn",
        "hell",
        "crap",
        "piss",
        "nigger",
        "nigga",
        "faggot",
        "fag",
        "kike",
        "spic",
        "chink",
        "wetback",
        "retard",
        "tranny",
    }
)

_WEAPON_TERMS: frozenset[str] = frozenset(
    {
        "gun",
        "guns",
        "pistol",
        "rifle",
        "shotgun",
        "firearm",
        "firearms",
        "handgun",
        "revolver",
        "glock",
        "ammunition",
        "ammo",
        "bullet",
        "bullets",
        "ar15",
        "ar-15",
        "knife",
        "knives",
        "machete",
        "blade",
        "semiautomatic",
        "magazine",
        "holster",
    }
)

_GRAPHIC_DISTRESS_TAGS: frozenset[str] = frozenset(
    {
        "gore_visible",
        "blood_pool",
        "graphic_injury",
        "distressed_victim_audio",
        "mutilation",
        "shocking_visual",
        "corpse_visible",
        "gunshot_wound",
        "stab_wound",
    }
)

_GRAPHIC_DISTRESS_TEXT: frozenset[str] = frozenset(
    {
        "gore",
        "gory",
        "bloodbath",
        "bloodsoaked",
        "mutilation",
        "dismember",
        "decapitat",
        "intestines",
        "corpse",
        "cadaver",
        "gunshot wound",
        "stab wound",
        "graphic injury",
        "screaming victim",
    }
)

# Cinematography phrases that must not trip the weapon term classifier.
_BENIGN_WEAPON_PHRASES: tuple[str, ...] = (
    "shooting tracking shot",
    "tracking shot",
)


@dataclass(frozen=True)
class FoiaIntroSlice:
    """FOIA source window mapped onto an episode-timeline segment."""

    foia_asset_id: str
    source_start_ms: int
    source_end_ms: int
    episode_start_ms: int
    episode_end_ms: int
    profanity_intervals_json: Sequence[Mapping[str, Any]] | str | None = None
    graphic_distress_tags: Sequence[str] = ()
    spoken_transcript: str = ""

    def __post_init__(self) -> None:
        if self.source_end_ms < self.source_start_ms:
            raise ValueError("source_end_ms must be >= source_start_ms")
        if self.episode_end_ms < self.episode_start_ms:
            raise ValueError("episode_end_ms must be >= episode_start_ms")

    def overlaps_intro(self, intro_end_ms: int = EPISODE_INTRO_END_MS) -> bool:
        return self.episode_start_ms < intro_end_ms and self.episode_end_ms > 0


@dataclass
class AdSenseGateResult:
    first_30s_adsense_safe: int
    passed: bool
    reason: str
    violations: list[str] = field(default_factory=list)

    def to_audit_fields(self) -> dict[str, Any]:
        return {
            "first_30s_adsense_safe": self.first_30s_adsense_safe,
            "adsense_gate_reason": None if self.passed else self.reason,
            "adsense_gate_violations": list(self.violations),
        }


def _normalize_token(word: str) -> str:
    return _TOKEN_RE.sub("", word.strip().lower())


def _strip_benign_phrases(text: str) -> str:
    lowered = text.lower()
    for phrase in _BENIGN_WEAPON_PHRASES:
        lowered = lowered.replace(phrase, " ")
    return lowered


def _tokenize(text: str) -> list[str]:
    cleaned = _strip_benign_phrases(text.lower())
    return [tok for tok in _TOKEN_RE.split(cleaned) if tok]


def find_profanity_terms(text: str) -> list[str]:
    hits: list[str] = []
    for token in _tokenize(text):
        norm = _normalize_token(token)
        if norm in _PROFANITY_WORDS:
            hits.append(norm)
    return hits


def find_weapon_terms(text: str) -> list[str]:
    hits: list[str] = []
    for token in _tokenize(text):
        norm = _normalize_token(token)
        if norm in _WEAPON_TERMS:
            hits.append(norm)
    return hits


def find_graphic_distress_in_text(text: str) -> list[str]:
    lowered = text.lower()
    hits: list[str] = []
    for phrase in _GRAPHIC_DISTRESS_TEXT:
        if phrase in lowered:
            hits.append(phrase)
    return hits


def find_graphic_distress_tags(tags: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for tag in tags:
        norm = tag.strip().lower().replace("-", "_")
        if norm in _GRAPHIC_DISTRESS_TAGS:
            hits.append(norm)
    return hits


def parse_profanity_intervals(
    raw: Sequence[Mapping[str, Any]] | str | None,
) -> list[dict[str, int | str]]:
    if raw is None:
        return []
    if isinstance(raw, str):
        if not raw.strip():
            return []
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise TypeError("profanity_intervals_json must decode to a list")
        raw = payload
    out: list[dict[str, int | str]] = []
    for item in raw:
        out.append(
            {
                "start_ms": int(item["start_ms"]),
                "end_ms": int(item["end_ms"]),
                "severity": str(item.get("severity", "moderate")),
            }
        )
    return out


def _intervals_overlap(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and a_end > b_start


def profanity_overlaps_source_window(
    profanity_intervals: Sequence[Mapping[str, Any]] | str | None,
    source_start_ms: int,
    source_end_ms: int,
) -> list[dict[str, int | str]]:
    """Return profanity intervals overlapping ``[source_start_ms, source_end_ms)``."""
    intervals = parse_profanity_intervals(profanity_intervals)
    overlapping: list[dict[str, int | str]] = []
    for item in intervals:
        start = int(item["start_ms"])
        end = int(item["end_ms"])
        if _intervals_overlap(start, end, source_start_ms, source_end_ms):
            overlapping.append(item)
    return overlapping


def _scan_text_bundle(text: str, *, prefix: str) -> list[str]:
    violations: list[str] = []
    for term in find_profanity_terms(text):
        violations.append(f"{prefix}:profanity:{term}")
    for term in find_weapon_terms(text):
        violations.append(f"{prefix}:weapon:{term}")
    for term in find_graphic_distress_in_text(text):
        violations.append(f"{prefix}:graphic_distress:{term}")
    return violations


@dataclass
class First30sAdSenseGate:
    """Evaluate opening narration and intro FOIA slices for AdSense yellow-icon risk."""

    intro_end_ms: int = EPISODE_INTRO_END_MS

    def evaluate(
        self,
        opening_narration: str,
        *,
        foia_intro_slices: Sequence[FoiaIntroSlice] = (),
    ) -> AdSenseGateResult:
        violations: list[str] = []
        violations.extend(_scan_text_bundle(opening_narration, prefix="narration"))

        for slice_ in foia_intro_slices:
            if not slice_.overlaps_intro(self.intro_end_ms):
                continue
            overlap = profanity_overlaps_source_window(
                slice_.profanity_intervals_json,
                slice_.source_start_ms,
                slice_.source_end_ms,
            )
            for hit in overlap:
                violations.append(
                    f"foia:{slice_.foia_asset_id}:profanity_interval:"
                    f"{hit['start_ms']}-{hit['end_ms']}"
                )
            for tag in find_graphic_distress_tags(slice_.graphic_distress_tags):
                violations.append(f"foia:{slice_.foia_asset_id}:graphic_distress_tag:{tag}")
            if slice_.spoken_transcript:
                violations.extend(
                    _scan_text_bundle(
                        slice_.spoken_transcript,
                        prefix=f"foia:{slice_.foia_asset_id}",
                    )
                )

        if not violations:
            return AdSenseGateResult(
                first_30s_adsense_safe=1,
                passed=True,
                reason=_REASON_CLEAN,
            )

        reason = _classify_primary_reason(violations)
        return AdSenseGateResult(
            first_30s_adsense_safe=0,
            passed=False,
            reason=reason,
            violations=violations,
        )


def _classify_primary_reason(violations: Sequence[str]) -> str:
    if any(":profanity" in v or "profanity_interval" in v for v in violations):
        if any("profanity_interval" in v for v in violations):
            return _REASON_FOIA_PROFANITY
        return _REASON_PROFANITY
    if any(":weapon:" in v for v in violations):
        return _REASON_WEAPON
    return _REASON_DISTRESS


def evaluate_first_30s_adsense_safe(
    opening_narration: str,
    *,
    foia_intro_slices: Sequence[FoiaIntroSlice] = (),
    intro_end_ms: int = EPISODE_INTRO_END_MS,
) -> AdSenseGateResult:
    """Convenience wrapper returning a full gate result."""
    return First30sAdSenseGate(intro_end_ms=intro_end_ms).evaluate(
        opening_narration,
        foia_intro_slices=foia_intro_slices,
    )