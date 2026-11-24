"""Fail-closed policy kill switch for documentary scout candidates.

``PolicyKillSwitchGate.evaluate`` decides whether the pipeline may proceed
with a candidate. The check is a pure function: it does not use the network,
the clock, or the filesystem.

A candidate is hard-rejected (``status == "REJECTED"`` and a
``policy_kill_reason``) when the case centers on any blocked category:

- a minor as victim, witness, or offender
- mass shooting
- terrorism
- child abuse
- an unconvicted suspect

Ambiguous minor involvement is a reject. An empty or missing disposition is
a reject. Adult defendants pass only with a standing conviction, including an
appellate review that leaves that conviction standing (``AFFIRMED`` or
``STANDING_CONVICTION``). Every other disposition fails closed.

The word "minor" in "minor count" is a charge-severity term, not evidence
that a child is involved.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

PASSED = "PASSED"
REJECTED = "REJECTED"

MINOR_CENTERED = "MINOR_CENTERED"
AMBIGUOUS_MINOR = "AMBIGUOUS_MINOR"
MASS_SHOOTING = "MASS_SHOOTING"
TERRORISM = "TERRORISM"
CHILD_ABUSE = "CHILD_ABUSE"
UNCONVICTED_SUSPECT = "UNCONVICTED_SUSPECT"
MISSING_DISPOSITION = "MISSING_DISPOSITION"

_REASON_PRIORITY: tuple[str, ...] = (
    CHILD_ABUSE,
    MASS_SHOOTING,
    TERRORISM,
    MINOR_CENTERED,
    AMBIGUOUS_MINOR,
    MISSING_DISPOSITION,
    UNCONVICTED_SUSPECT,
)

_STANDING_DISPOSITIONS = frozenset(
    {
        "AFFIRMED",
        "STANDING_CONVICTION",
        "CONVICTED",
    }
)

_CATEGORY_TOKENS: dict[str, str] = {
    "child_abuse": CHILD_ABUSE,
    "mass_shooting": MASS_SHOOTING,
    "terrorism": TERRORISM,
    "terrorist_attack": TERRORISM,
    "minor": MINOR_CENTERED,
    "minor_victim": MINOR_CENTERED,
    "minor_witness": MINOR_CENTERED,
    "minor_offender": MINOR_CENTERED,
    "minor_defendant": MINOR_CENTERED,
    "juvenile": MINOR_CENTERED,
    "juvenile_victim": MINOR_CENTERED,
    "juvenile_witness": MINOR_CENTERED,
    "juvenile_offender": MINOR_CENTERED,
    "underage": MINOR_CENTERED,
    "ambiguous_minor": AMBIGUOUS_MINOR,
    "ambiguous_minor_involvement": AMBIGUOUS_MINOR,
    "unconvicted": UNCONVICTED_SUSPECT,
    "unconvicted_suspect": UNCONVICTED_SUSPECT,
}

_TEXT_PHRASES: tuple[tuple[str, str], ...] = (
    ("child abuse", CHILD_ABUSE),
    ("abuse of a child", CHILD_ABUSE),
    ("abuse of a minor", CHILD_ABUSE),
    ("mass shooting", MASS_SHOOTING),
    ("mass-shooting", MASS_SHOOTING),
    ("terrorism", TERRORISM),
    ("terrorist attack", TERRORISM),
    ("minor victim", MINOR_CENTERED),
    ("child victim", MINOR_CENTERED),
    ("juvenile victim", MINOR_CENTERED),
    ("underage victim", MINOR_CENTERED),
    ("minor witness", MINOR_CENTERED),
    ("child witness", MINOR_CENTERED),
    ("juvenile witness", MINOR_CENTERED),
    ("minor offender", MINOR_CENTERED),
    ("juvenile offender", MINOR_CENTERED),
    ("underage offender", MINOR_CENTERED),
    ("minor defendant", MINOR_CENTERED),
    ("juvenile defendant", MINOR_CENTERED),
    ("underage defendant", MINOR_CENTERED),
    ("ambiguous minor", AMBIGUOUS_MINOR),
    ("possibly a minor", AMBIGUOUS_MINOR),
    ("possible minor", AMBIGUOUS_MINOR),
    ("may be a minor", AMBIGUOUS_MINOR),
    ("age unknown", AMBIGUOUS_MINOR),
    ("age unclear", AMBIGUOUS_MINOR),
    ("minor status unknown", AMBIGUOUS_MINOR),
    ("unclear whether a minor", AMBIGUOUS_MINOR),
    ("unknown whether a minor", AMBIGUOUS_MINOR),
)

_CATEGORY_FIELDS = (
    "centers_on",
    "categories",
    "offense_categories",
    "policy_tags",
    "blocked_categories",
)

_TEXT_FIELDS = (
    "case_focus",
    "summary",
    "offense",
    "offense_description",
    "title",
    "charge",
    "charges",
    "description",
    "narrative_focus",
    "focus",
)

_PERSON_LIST_FIELDS = (
    "subjects",
    "parties",
    "persons",
    "people",
    "involved_persons",
)

_MINOR_FLAG_FIELDS = (
    "victim_is_minor",
    "witness_is_minor",
    "offender_is_minor",
    "defendant_is_minor",
    "suspect_is_minor",
)

_AGE_STATUS_FIELDS = (
    "defendant_age_status",
    "suspect_age_status",
    "offender_age_status",
    "victim_age_status",
    "witness_age_status",
)

_AGE_VALUE_FIELDS = (
    "defendant_age",
    "suspect_age",
    "offender_age",
    "victim_age",
    "witness_age",
)

_AGE_ADULT = frozenset({"adult", "adult_convicted"})
_AGE_MINOR = frozenset({"minor", "juvenile", "child", "underage"})
_AGE_AMBIGUOUS = frozenset(
    {
        "unknown",
        "ambiguous",
        "unclear",
        "unspecified",
        "undetermined",
    }
)
_YES = frozenset({"true", "yes", "y", "1"})
_NO = frozenset({"false", "no", "n", "0", "none", "adult", "adult_only", "na"})
_MINOR_ROLES = frozenset(
    {
        "victim",
        "witness",
        "offender",
        "defendant",
        "suspect",
        "perpetrator",
        "accused",
    }
)

_TOKEN_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class KillSwitchDecision:
    """Gate result. ``REJECTED`` always carries ``policy_kill_reason``."""

    status: str
    policy_kill_reason: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {PASSED, REJECTED}:
            raise ValueError(f"unexpected status {self.status!r}")
        if self.status == REJECTED and not self.policy_kill_reason:
            raise ValueError("REJECTED requires policy_kill_reason")
        if self.status == PASSED and self.policy_kill_reason is not None:
            raise ValueError("PASSED cannot carry policy_kill_reason")

    @property
    def passed(self) -> bool:
        return self.status == PASSED

    @property
    def rejected(self) -> bool:
        return self.status == REJECTED


def _norm_token(value: str) -> str:
    return _TOKEN_RE.sub("_", value.strip().lower()).strip("_")


def _as_mapping(candidate: Any) -> Mapping[str, Any]:
    if isinstance(candidate, Mapping):
        return candidate
    dump = getattr(candidate, "model_dump", None)
    if callable(dump):
        data = dump()
        if isinstance(data, Mapping):
            return data
    raw = getattr(candidate, "__dict__", None)
    if isinstance(raw, dict):
        return {key: value for key, value in raw.items() if not str(key).startswith("_")}
    raise TypeError("candidate must be a mapping or an object with attributes")


def _iter_tokens(value: Any) -> list[str]:
    if value is None or isinstance(value, bool):
        return []
    if isinstance(value, str):
        return [_norm_token(part) for part in re.split(r"[,|/]", value) if part.strip()]
    if isinstance(value, (list, tuple, set, frozenset)):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_iter_tokens(item))
        return tokens
    return [_norm_token(str(value))]


def _reason_for_token(token: str) -> str | None:
    known = _CATEGORY_TOKENS.get(token)
    if known is not None:
        return known
    if "child_abuse" in token:
        return CHILD_ABUSE
    if "mass_shooting" in token:
        return MASS_SHOOTING
    if "terror" in token:
        return TERRORISM
    if "unconvicted" in token:
        return UNCONVICTED_SUSPECT
    if "ambiguous" in token or "unknown" in token:
        if "minor" in token or "juvenile" in token or "child" in token:
            return AMBIGUOUS_MINOR
    if "minor" in token or "juvenile" in token or token in {"child", "underage"}:
        return MINOR_CENTERED
    return None


def _tri(value: Any) -> str:
    """Classify an explicit flag as yes, no, or ambiguous."""
    if value is True or value == 1:
        return "yes"
    if value is False or value == 0:
        return "no"
    if value is None:
        return "ambiguous"
    if isinstance(value, str):
        token = _norm_token(value)
        if token in _YES or token in _MINOR_ROLES or token in _AGE_MINOR:
            return "yes"
        if token in _NO or token in _AGE_ADULT:
            return "no"
        if token in _AGE_AMBIGUOUS or token == "":
            return "ambiguous"
    return "ambiguous"


def _age_class(person: Mapping[str, Any]) -> str:
    """Return adult, minor, ambiguous, or unspecified."""
    if "is_minor" in person:
        flag = _tri(person.get("is_minor"))
        if flag == "yes":
            return "minor"
        if flag == "no":
            return "adult"
        return "ambiguous"
    if "age" in person or "age_years" in person:
        raw = person["age"] if "age" in person else person.get("age_years")
        return _numeric_or_label_age(raw)
    if "age_status" in person or "age_band" in person:
        raw = person.get("age_status", person.get("age_band"))
        return _label_age(raw)
    return "unspecified"


def _numeric_or_label_age(raw: Any) -> str:
    if raw is None or isinstance(raw, bool):
        return "ambiguous"
    if isinstance(raw, (int, float)):
        if raw < 0:
            return "ambiguous"
        return "minor" if raw < 18 else "adult"
    if isinstance(raw, str):
        text = raw.strip().lower()
        if text.isdigit():
            return "minor" if int(text) < 18 else "adult"
        return _label_age(text)
    return "ambiguous"


def _label_age(raw: Any) -> str:
    if raw is None:
        return "ambiguous"
    token = _norm_token(str(raw))
    if token in _AGE_ADULT:
        return "adult"
    if token in _AGE_MINOR:
        return "minor"
    return "ambiguous"


def _contains_phrase(haystack: str, phrase: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(phrase) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def _from_categories(candidate: Mapping[str, Any], reasons: set[str]) -> None:
    for field in _CATEGORY_FIELDS:
        if field not in candidate:
            continue
        for token in _iter_tokens(candidate.get(field)):
            reason = _reason_for_token(token)
            if reason is not None:
                reasons.add(reason)


def _from_text(candidate: Mapping[str, Any], reasons: set[str]) -> None:
    chunks: list[str] = []
    for field in _TEXT_FIELDS:
        value = candidate.get(field)
        if isinstance(value, str) and value.strip():
            chunks.append(value)
    centers = candidate.get("centers_on")
    if isinstance(centers, str) and centers.strip():
        chunks.append(centers)
    if not chunks:
        return
    haystack = " ".join(chunks).lower()
    for phrase, reason in _TEXT_PHRASES:
        if _contains_phrase(haystack, phrase):
            reasons.add(reason)


def _from_minor_flags(candidate: Mapping[str, Any], reasons: set[str]) -> None:
    for field in _MINOR_FLAG_FIELDS:
        if field not in candidate:
            continue
        flag = _tri(candidate.get(field))
        if flag == "yes":
            reasons.add(MINOR_CENTERED)
        elif flag == "ambiguous":
            reasons.add(AMBIGUOUS_MINOR)

    for field in ("involves_minor", "minor_involvement"):
        if field not in candidate:
            continue
        flag = _tri(candidate.get(field))
        if flag == "yes":
            reasons.add(MINOR_CENTERED)
        elif flag == "ambiguous":
            reasons.add(AMBIGUOUS_MINOR)

    if "minor_role" not in candidate:
        return
    role = candidate.get("minor_role")
    if not isinstance(role, str):
        reasons.add(AMBIGUOUS_MINOR)
        return
    token = _norm_token(role)
    if token in _NO:
        return
    if token in _MINOR_ROLES or token in _AGE_MINOR:
        reasons.add(MINOR_CENTERED)
        return
    reasons.add(AMBIGUOUS_MINOR)


def _record_age(kind: str, reasons: set[str]) -> None:
    if kind == "minor":
        reasons.add(MINOR_CENTERED)
    elif kind == "ambiguous":
        reasons.add(AMBIGUOUS_MINOR)


def _from_people(candidate: Mapping[str, Any], reasons: set[str]) -> None:
    for field in _AGE_STATUS_FIELDS:
        if field not in candidate:
            continue
        _record_age(_label_age(candidate.get(field)), reasons)
    for field in _AGE_VALUE_FIELDS:
        if field not in candidate:
            continue
        _record_age(_numeric_or_label_age(candidate.get(field)), reasons)

    for field in _PERSON_LIST_FIELDS:
        if field not in candidate:
            continue
        people = candidate.get(field)
        if people is None:
            reasons.add(AMBIGUOUS_MINOR)
            continue
        if isinstance(people, Mapping):
            people = [people]
        if not isinstance(people, (list, tuple)):
            reasons.add(AMBIGUOUS_MINOR)
            continue
        for person in people:
            if not isinstance(person, Mapping):
                reasons.add(AMBIGUOUS_MINOR)
                continue
            _record_age(_age_class(person), reasons)


def _disposition_reason(candidate: Mapping[str, Any]) -> str | None:
    has_status = "disposition_status" in candidate or "disposition" in candidate
    raw = candidate.get("disposition_status", candidate.get("disposition"))
    text = "" if raw is None else str(raw).strip()
    if not has_status or text == "":
        return MISSING_DISPOSITION
    standing = _norm_token(text).upper() in _STANDING_DISPOSITIONS
    if "conviction_confirmed" in candidate:
        flag = _tri(candidate.get("conviction_confirmed"))
        if flag != "yes":
            return UNCONVICTED_SUSPECT
    if standing:
        return None
    return UNCONVICTED_SUSPECT


def classify(candidate: Any) -> KillSwitchDecision:
    """Return the fail-closed decision for one candidate."""
    data = _as_mapping(candidate)
    reasons: set[str] = set()
    _from_categories(data, reasons)
    _from_text(data, reasons)
    _from_minor_flags(data, reasons)
    _from_people(data, reasons)
    disposition = _disposition_reason(data)
    if disposition is not None:
        reasons.add(disposition)
    if not reasons:
        return KillSwitchDecision(status=PASSED)
    reason = next(item for item in _REASON_PRIORITY if item in reasons)
    return KillSwitchDecision(status=REJECTED, policy_kill_reason=reason)


class PolicyKillSwitchGate:
    """Binary fail-closed classifier for scout candidates."""

    def evaluate(self, candidate: Any) -> KillSwitchDecision:
        return classify(candidate)
