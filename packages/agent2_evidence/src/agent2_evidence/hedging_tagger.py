"""Source-tier hedging tagger for the temporal fact ledger.

Composite drafts that mix a verified court holding with secondary news rumor
claims are split into separate facts. Every ``news_report`` row is forced to
``hedging_required = 1`` and gets a fixed attribution prefix on ``event_summary``.
``court_ruling`` and ``police_affidavit`` facts stay unhedged.

Python mirrors ``trg_fact_news_hedging_insert`` / ``trg_fact_news_hedging_update``
(RULE_09) so in-memory ledgers cannot bypass the same invariant before SQLite
insert. This module does not open a database or edit ``schema/pipeline.sql``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

SourceType = Literal["court_ruling", "police_affidavit", "news_report"]

NEWS_ATTRIBUTION_PREFIX = "News accounts reported that "
RULE_09_MESSAGE = "RULE_09: news_report fact must have hedging_required = 1"

_COMPOSITE_SPLITS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r";\s*however,\s*", re.IGNORECASE), "court_then_news"),
    (re.compile(r";\s*but\s+", re.IGNORECASE), "court_then_news"),
    (re.compile(r"\.\s+Meanwhile,\s+", re.IGNORECASE), "court_then_news"),
)

_COURT_CLAUSE = re.compile(
    r"\b(?:court|appellate|ruling|affirmed|vacated|remanded|held\s+that|justice|judge)\b",
    re.IGNORECASE,
)
_NEWS_CLAUSE = re.compile(
    r"\b(?:news|reported|outlets?|tabloid|rumou?r|alleged(?:ly)?|broadcast|newspaper|media)\b",
    re.IGNORECASE,
)
_ATTRIBUTION_RE = re.compile(r"^News accounts reported that\s+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class TaggedFact:
    """One ledger-ready fact after hedging and optional composite split."""

    fact_id: str
    case_id: str
    datetime_iso: str
    event_summary: str
    physical_clues_json: list[str]
    location_text: str
    source_type: SourceType
    source_doc_id: str
    citation_locator: str
    hedging_required: int
    contradicts_json: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "case_id": self.case_id,
            "datetime_iso": self.datetime_iso,
            "event_summary": self.event_summary,
            "physical_clues_json": list(self.physical_clues_json),
            "location_text": self.location_text,
            "source_type": self.source_type,
            "source_doc_id": self.source_doc_id,
            "citation_locator": self.citation_locator,
            "hedging_required": self.hedging_required,
            "contradicts_json": list(self.contradicts_json),
        }


def hedging_flag_for(source_type: SourceType) -> int:
    return 1 if source_type == "news_report" else 0


def enforce_rule_09(source_type: SourceType, hedging_required: int) -> int:
    """Raise ``ValueError`` when RULE_09 would abort an SQLite insert."""
    if source_type == "news_report" and hedging_required == 0:
        raise ValueError(RULE_09_MESSAGE)
    return hedging_required


def prefix_news_attribution(event_summary: str) -> str:
    text = event_summary.strip()
    if not text:
        return NEWS_ATTRIBUTION_PREFIX.rstrip()
    if _ATTRIBUTION_RE.match(text):
        return text[0].upper() + text[1:] if text else text
    body = text[0].lower() + text[1:] if len(text) > 1 else text.lower()
    return f"{NEWS_ATTRIBUTION_PREFIX}{body}"


def _coerce_fact(raw: Mapping[str, Any]) -> dict[str, Any]:
    clues = raw.get("physical_clues_json", [])
    if isinstance(clues, str):
        clues = []
    contradicts = raw.get("contradicts_json", [])
    if isinstance(contradicts, str):
        contradicts = []
    hedge = raw.get("hedging_required", 0)
    if isinstance(hedge, bool):
        hedge = int(hedge)
    return {
        "fact_id": str(raw["fact_id"]),
        "case_id": str(raw["case_id"]),
        "datetime_iso": str(raw["datetime_iso"]),
        "event_summary": str(raw["event_summary"]),
        "physical_clues_json": list(clues),
        "location_text": str(raw["location_text"]),
        "source_type": raw["source_type"],
        "source_doc_id": str(raw["source_doc_id"]),
        "citation_locator": str(raw["citation_locator"]),
        "hedging_required": int(hedge),
        "contradicts_json": list(contradicts),
    }


def _split_composite(fact: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = str(fact["event_summary"])
    for pattern, _kind in _COMPOSITE_SPLITS:
        parts = pattern.split(summary, maxsplit=1)
        if len(parts) != 2:
            continue
        court_text, news_text = parts[0].strip(), parts[1].strip()
        if not court_text or not news_text:
            continue
        if not _COURT_CLAUSE.search(court_text) or not _NEWS_CLAUSE.search(news_text):
            continue
        court = _coerce_fact(fact)
        news = _coerce_fact(fact)
        court["fact_id"] = f"{fact['fact_id']}__court"
        news["fact_id"] = f"{fact['fact_id']}__news"
        court["event_summary"] = _sentence(court_text)
        news["event_summary"] = _sentence(news_text)
        court["source_type"] = "court_ruling"
        news["source_type"] = "news_report"
        news_doc = fact.get("news_source_doc_id")
        if news_doc:
            news["source_doc_id"] = str(news_doc)
        news_cite = fact.get("news_citation_locator")
        if news_cite:
            news["citation_locator"] = str(news_cite)
        return [court, news]
    return [_coerce_fact(fact)]


def _sentence(text: str) -> str:
    cleaned = text.strip()
    if not cleaned:
        return cleaned
    if cleaned[-1] not in ".!?":
        cleaned = f"{cleaned}."
    return cleaned


def _finalize(fact: MutableMapping[str, Any]) -> TaggedFact:
    source = fact["source_type"]
    if source not in ("court_ruling", "police_affidavit", "news_report"):
        raise ValueError(f"unsupported source_type: {source!r}")
    hedge = hedging_flag_for(source)
    enforce_rule_09(source, hedge)
    summary = str(fact["event_summary"])
    if source == "news_report":
        summary = prefix_news_attribution(summary)
        hedge = 1
    elif _ATTRIBUTION_RE.match(summary):
        raise ValueError("court_ruling and police_affidavit must not carry news attribution")
    return TaggedFact(
        fact_id=str(fact["fact_id"]),
        case_id=str(fact["case_id"]),
        datetime_iso=str(fact["datetime_iso"]),
        event_summary=summary,
        physical_clues_json=list(fact["physical_clues_json"]),
        location_text=str(fact["location_text"]),
        source_type=source,
        source_doc_id=str(fact["source_doc_id"]),
        citation_locator=str(fact["citation_locator"]),
        hedging_required=hedge,
        contradicts_json=list(fact["contradicts_json"]),
    )


def tag_facts_for_hedging(facts: Sequence[Mapping[str, Any]]) -> list[TaggedFact]:
    """Split composites, apply RULE_09 hedging flags, and prefix news attribution."""
    out: list[TaggedFact] = []
    for raw in facts:
        for piece in _split_composite(raw):
            out.append(_finalize(piece))
    return out


def validate_hedging_before_insert(row: Mapping[str, Any]) -> None:
    """Pre-insert guard matching ``trg_fact_news_hedging_insert``."""
    enforce_rule_09(row["source_type"], int(row["hedging_required"]))


def validate_hedging_before_update(row: Mapping[str, Any]) -> None:
    """Pre-update guard matching ``trg_fact_news_hedging_update``."""
    enforce_rule_09(row["source_type"], int(row["hedging_required"]))