"""Extract evidence-backed turning-point beats from a temporal fact ledger.

Turning points are analytical editorial beats tied to primary-record citations.
Output is procedural reporting only — never legal advice or interpretive counsel.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

MIN_TURNING_POINTS = 3
REJECTED_LOW_TWIST_DENSITY = "REJECTED_LOW_TWIST_DENSITY"

TwistKind = Literal["discredited_alibi", "forensic_match", "appellate_holding"]
SourceType = Literal["court_ruling", "police_affidavit", "news_report"]
ExtractionStatus = Literal["OK", "REJECTED"]

_FORENSIC_CLUE_WORDS = frozenset(
    {
        "dna",
        "fingerprint",
        "ballistic",
        "ballistics",
        "fiber",
        "bloodstain",
        "codis",
        "mtdna",
        "latent",
        "shell",
        "cartridge",
    }
)
_FORENSIC_SUMMARY_RE = re.compile(
    r"\b(dna|fingerprint|ballistic|ballistics|forensic\s+match|"
    r"mt-?dna|codis|latent\s+print)\b",
    re.IGNORECASE,
)
_ALIBI_DISCREDIT_RE = re.compile(
    r"\b(alibi).{0,80}\b(discredited|contradicted|refuted|undermined|"
    r"inconsistent|improbable)\b",
    re.IGNORECASE,
)
_ALIBI_DISCREDIT_REVERSE = re.compile(
    r"\b(discredited|contradicted|refuted|undermined|inconsistent).{0,80}\b(alibi)\b",
    re.IGNORECASE,
)
_APPELLATE_HOLDING_RE = re.compile(
    r"\b(appellate|panel|majority|court\s+held|holding|affirmed|affirms)\b",
    re.IGNORECASE,
)

_LEGAL_ADVICE_PATTERNS = (
    re.compile(r"\byou\s+should\b", re.IGNORECASE),
    re.compile(r"\bconsult\s+(an?\s+)?(lawyer|attorney)\b", re.IGNORECASE),
    re.compile(r"\blegal\s+advice\b", re.IGNORECASE),
    re.compile(r"\bthey\s+(are|were)\s+guilty\b", re.IGNORECASE),
    re.compile(r"\bthey\s+(are|were)\s+innocent\b", re.IGNORECASE),
    re.compile(r"\bproving\s+guilt\b", re.IGNORECASE),
    re.compile(r"\bproving\s+innocence\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class TwistFact:
    fact_id: str
    datetime_iso: str
    event_summary: str
    source_type: SourceType
    citation_locator: str
    physical_clues: tuple[str, ...] = ()
    contradicts_fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FactLedger:
    case_id: str
    facts: tuple[TwistFact, ...]


@dataclass(frozen=True, slots=True)
class TurningPointBeat:
    beat_id: str
    twist_kind: TwistKind
    fact_id: str
    datetime_iso: str
    citation_locator: str
    source_type: SourceType
    editorial_analysis: str
    record_anchor: str


@dataclass(frozen=True, slots=True)
class TurningPointExtractionResult:
    status: ExtractionStatus
    reason: str | None
    beats: tuple[TurningPointBeat, ...]
    turning_point_count: int
    anti_legal_persona_passed: bool

    @property
    def rejected(self) -> bool:
        return self.status == "REJECTED"

    @property
    def accepted(self) -> bool:
        return self.status == "OK"


def extract_turning_points(ledger: FactLedger) -> TurningPointExtractionResult:
    """Extract turning-point beats or reject thin cases early."""
    classified: list[tuple[TwistFact, TwistKind]] = []
    facts_by_id = {fact.fact_id: fact for fact in ledger.facts}

    for fact in ledger.facts:
        kind = _classify_twist(fact, facts_by_id)
        if kind is not None:
            classified.append((fact, kind))

    if len(classified) < MIN_TURNING_POINTS:
        return TurningPointExtractionResult(
            status="REJECTED",
            reason=REJECTED_LOW_TWIST_DENSITY,
            beats=(),
            turning_point_count=len(classified),
            anti_legal_persona_passed=True,
        )

    beats: list[TurningPointBeat] = []
    for index, (fact, kind) in enumerate(classified, start=1):
        analysis, anchor = _editorial_copy(fact, kind)
        if not _anti_legal_persona_passed(analysis):
            return TurningPointExtractionResult(
                status="REJECTED",
                reason="REJECTED_LEGAL_PERSONA",
                beats=(),
                turning_point_count=len(classified),
                anti_legal_persona_passed=False,
            )
        beats.append(
            TurningPointBeat(
                beat_id=f"tp_{ledger.case_id}_{index:02d}",
                twist_kind=kind,
                fact_id=fact.fact_id,
                datetime_iso=fact.datetime_iso,
                citation_locator=fact.citation_locator,
                source_type=fact.source_type,
                editorial_analysis=analysis,
                record_anchor=anchor,
            )
        )

    return TurningPointExtractionResult(
        status="OK",
        reason=None,
        beats=tuple(beats),
        turning_point_count=len(beats),
        anti_legal_persona_passed=True,
    )


def _classify_twist(
    fact: TwistFact,
    facts_by_id: dict[str, TwistFact],
) -> TwistKind | None:
    if _is_appellate_holding(fact):
        return "appellate_holding"
    if _is_forensic_match(fact):
        return "forensic_match"
    if _is_discredited_alibi(fact, facts_by_id):
        return "discredited_alibi"
    return None


def _is_appellate_holding(fact: TwistFact) -> bool:
    if fact.source_type != "court_ruling":
        return False
    return bool(_APPELLATE_HOLDING_RE.search(fact.event_summary))


def _is_forensic_match(fact: TwistFact) -> bool:
    if fact.physical_clues and any(
        _clue_is_forensic(clue) for clue in fact.physical_clues
    ):
        return True
    return bool(_FORENSIC_SUMMARY_RE.search(fact.event_summary))


def _clue_is_forensic(clue: str) -> bool:
    tokens = {
        token.strip(".,;:")
        for token in re.split(r"[\s/\-]+", clue.casefold())
        if token.strip(".,;:")
    }
    return bool(tokens & _FORENSIC_CLUE_WORDS) or "match" in clue.casefold()


def _is_discredited_alibi(
    fact: TwistFact,
    facts_by_id: dict[str, TwistFact],
) -> bool:
    summary = fact.event_summary
    if _ALIBI_DISCREDIT_RE.search(summary) or _ALIBI_DISCREDIT_REVERSE.search(summary):
        return True
    if "alibi" not in summary.casefold():
        return False
    if any(
        word in summary.casefold()
        for word in (
            "discredited",
            "contradicted",
            "refuted",
            "undermined",
            "inconsistent",
            "surveillance",
            "toll record",
            "receipt",
            "cell-site",
            "cell site",
        )
    ):
        return True
    for other_id in fact.contradicts_fact_ids:
        other = facts_by_id.get(other_id)
        if other is None:
            continue
        if "alibi" in other.event_summary.casefold():
            return True
    return False


def _editorial_copy(fact: TwistFact, kind: TwistKind) -> tuple[str, str]:
    source_label = _source_label(fact.source_type)
    anchor = (
        f"According to the {source_label} at {fact.citation_locator}, "
        f"the record states: {fact.event_summary}"
    )
    if kind == "discredited_alibi":
        analysis = (
            f"The documentary record documents how the suspect's earlier alibi account "
            f"no longer aligns with later {source_label} material cited at "
            f"{fact.citation_locator}; the timeline entry is presented for editorial "
            f"context rather than as interpretive counsel."
        )
    elif kind == "forensic_match":
        clue_hint = ""
        if fact.physical_clues:
            joined = ", ".join(fact.physical_clues[:3])
            clue_hint = f" Physical items noted in the ledger include {joined}."
        analysis = (
            f"A {source_label} entry at {fact.citation_locator} ties a forensic "
            f"comparison to items described in the case file.{clue_hint} "
            f"The narration reports what the document says without instructing viewers "
            f"on legal outcomes."
        )
    else:
        analysis = (
            f"The appellate {source_label} at {fact.citation_locator} records a "
            f"published holding in the procedural posture of the appeal. "
            f"Editorial coverage quotes the disposition language and stays within "
            f"objective procedural reporting."
        )
    return analysis, anchor


def _source_label(source_type: SourceType) -> str:
    return {
        "court_ruling": "appellate opinion",
        "police_affidavit": "police affidavit",
        "news_report": "news report",
    }[source_type]


def _anti_legal_persona_passed(text: str) -> bool:
    return not any(pattern.search(text) for pattern in _LEGAL_ADVICE_PATTERNS)