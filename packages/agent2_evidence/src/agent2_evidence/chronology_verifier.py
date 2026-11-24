"""Temporal chronology consistency and citation verifier.

Validates ``TemporalFactLedger`` rows for timezone-aware ISO-8601 timestamps,
physically plausible travel between locations, and resolvable ``citation_locator``
substrings inside cited ``primary_documents`` text.

DST fall-back wall times with different UTC offsets (for example
``2019-11-03T01:30:00-04:00`` vs ``2019-11-03T01:30:00-05:00``) normalize to
distinct UTC instants and are never treated as duplicates.

This module does not open sockets or read the database. Callers supply document
text keyed by ``source_doc_id``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from shared_contracts.models import TemporalFact, TemporalFactLedger

VERIFIER_ID = "chronology-verifier@1"

_ISO_OFFSET = re.compile(
    r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(Z|[+-]\d{2}:\d{2})$"
)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class ChronologyIssue:
    fact_id: str
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ChronologyVerdict:
    """Outcome of chronology and citation verification."""

    passed: bool
    issues: tuple[ChronologyIssue, ...]
    utc_by_fact_id: dict[str, datetime]

    @property
    def issue_codes(self) -> frozenset[str]:
        return frozenset(issue.code for issue in self.issues)


TravelLookup = Callable[[str, str], int | None]


def parse_utc_instant(datetime_iso: str) -> datetime:
    """Return an aware UTC ``datetime`` or raise ``ValueError``."""
    match = _ISO_OFFSET.fullmatch(datetime_iso)
    if match is None:
        raise ValueError("datetime_iso must include an explicit UTC offset or Z")
    body, offset = match.groups()
    if offset == "Z":
        offset = "+00:00"
    parsed = datetime.fromisoformat(f"{body}{offset}")
    return parsed.astimezone(UTC)


def _normalize_location(location_text: str) -> str:
    return _WHITESPACE.sub(" ", location_text.strip().casefold())


def _locator_in_text(locator: str, document_text: str) -> bool:
    if not locator.strip():
        return False
    if locator in document_text:
        return True
    collapsed_locator = _WHITESPACE.sub(" ", locator.strip())
    collapsed_doc = _WHITESPACE.sub(" ", document_text)
    return collapsed_locator in collapsed_doc


def verify_chronology(
    ledger: TemporalFactLedger,
    document_text_by_doc_id: Mapping[str, str],
    *,
    travel_minutes_lookup: TravelLookup | None = None,
    default_travel_minutes: int = 60,
) -> ChronologyVerdict:
    """Verify ledger facts for time, travel, and citation invariants."""
    issues: list[ChronologyIssue] = []
    utc_by_fact: dict[str, datetime] = {}
    iso_seen: dict[str, str] = {}

    ordered: list[tuple[datetime, TemporalFact]] = []

    for fact in ledger.facts:
        try:
            instant = parse_utc_instant(fact.datetime_iso)
        except ValueError:
            issues.append(
                ChronologyIssue(
                    fact.fact_id,
                    "MISSING_UTC_OFFSET",
                    "datetime_iso must include an explicit UTC offset or Z",
                )
            )
            continue

        utc_by_fact[fact.fact_id] = instant
        ordered.append((instant, fact))

        prior = iso_seen.get(fact.datetime_iso)
        if prior is not None and prior != fact.fact_id:
            issues.append(
                ChronologyIssue(
                    fact.fact_id,
                    "DUPLICATE_TIMESTAMP",
                    f"duplicate datetime_iso {fact.datetime_iso!r} shared with {prior}",
                )
            )
        else:
            iso_seen[fact.datetime_iso] = fact.fact_id

        doc_text = document_text_by_doc_id.get(fact.source_doc_id)
        if doc_text is None:
            issues.append(
                ChronologyIssue(
                    fact.fact_id,
                    "MISSING_DOCUMENT",
                    f"no text for source_doc_id {fact.source_doc_id!r}",
                )
            )
        elif not fact.citation_locator.strip():
            issues.append(
                ChronologyIssue(
                    fact.fact_id,
                    "MISSING_CITATION_LOCATOR",
                    "citation_locator must be non-empty",
                )
            )
        elif not _locator_in_text(fact.citation_locator, doc_text):
            issues.append(
                ChronologyIssue(
                    fact.fact_id,
                    "CITATION_UNRESOLVED",
                    f"citation_locator {fact.citation_locator!r} not found in cited document",
                )
            )

    ordered.sort(key=lambda row: (row[0], row[1].fact_id))

    for idx in range(1, len(ordered)):
        prev_instant, prev_fact = ordered[idx - 1]
        next_instant, next_fact = ordered[idx]
        prev_loc = _normalize_location(prev_fact.location_text)
        next_loc = _normalize_location(next_fact.location_text)
        if prev_loc == next_loc:
            continue

        gap_minutes = (next_instant - prev_instant).total_seconds() / 60.0
        if gap_minutes < 0:
            continue

        required: int | None = None
        if travel_minutes_lookup is not None:
            required = travel_minutes_lookup(
                prev_fact.location_text, next_fact.location_text
            )
            if required is None:
                required = travel_minutes_lookup(
                    next_fact.location_text, prev_fact.location_text
                )
        if required is None:
            required = default_travel_minutes

        if gap_minutes < required:
            issues.append(
                ChronologyIssue(
                    next_fact.fact_id,
                    "IMPOSSIBLE_TRAVEL",
                    (
                        f"{gap_minutes:.0f} minute gap from {prev_fact.location_text!r} to "
                        f"{next_fact.location_text!r} requires at least {required} minutes"
                    ),
                )
            )

    return ChronologyVerdict(
        passed=not issues, issues=tuple(issues), utc_by_fact_id=utc_by_fact
    )


def load_document_texts(
    primary_documents: Sequence[Mapping[str, Any]],
    read_text: Callable[[str], str],
) -> dict[str, str]:
    """Build ``doc_id -> text`` from ``primary_documents`` rows and a path reader."""
    out: dict[str, str] = {}
    for row in primary_documents:
        doc_id = str(row["doc_id"])
        path = str(row["local_text_path"])
        out[doc_id] = read_text(path)
    return out