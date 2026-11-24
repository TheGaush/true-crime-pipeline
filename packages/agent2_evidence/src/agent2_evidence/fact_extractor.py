"""Tool-less temporal fact ledger extractor (`evidence-ledger-extractor@3`).

The extractor returns data. It does not open a database, call tools, or
reach the network. Untrusted filings are wrapped in a random nonce tag.
`</data>` and `IGNORE PREVIOUS INSTRUCTIONS` stay data inside that tag and
are stripped from extracted facts so they cannot act as commands.

`source_type` is taken from the cited `primary_documents` row. Names of
unconvicted witnesses, neighbors, coworkers, family, and cleared alternate
suspects are replaced with role aliases. The convicted defendant named on
the case record is left in place. `anonymization_status` moves from
`NOT_STARTED` to `IN_REVIEW` only.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import shlex
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from shared_contracts.models import TemporalFactLedger
from shared_contracts.version import CONTRACT_VERSION

PROMPT_CONTRACT_ID = "evidence-ledger-extractor@3"
TOOLS_ENABLED = False
WRITES_DATABASE = False

_SOURCE_TYPES = ("court_ruling", "police_affidavit", "news_report")
_DOC_TYPE_TO_SOURCE = {
    "court_ruling": "court_ruling",
    "police_affidavit": "police_affidavit",
    "news_text_only": "news_report",
    "news_report": "news_report",
}
_STANDING_DISPOSITIONS = frozenset({"AFFIRMED", "STANDING_CONVICTION"})
_NONCE_RE = re.compile(r"^[0-9a-f]{4}$")
_ISO_DT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})$")
_ISO_SEARCH = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:\d{2})")
_TAG_RE = re.compile(r"<\s*/?\s*[A-Za-z][^>\n]*>")
_FACT_SPLIT = re.compile(r"(?=^FACT\b)", re.MULTILINE)
_ENTITY_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_NAME = r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}"
_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

_ROLE_PREFIX = (
    r"(?:cleared\s+alternate\s+suspects|cleared\s+alternate\s+suspect|"
    r"unconvicted\s+suspects|unconvicted\s+suspect|"
    r"alternate\s+suspects|alternate\s+suspect|"
    r"cleared\s+suspects|cleared\s+suspect|"
    r"eyewitnesses|eyewitness|witnesses|witness|"
    r"neighbours|neighbour|neighbors|neighbor|"
    r"co-workers|coworkers|co-worker|coworker|colleagues|colleague|"
    r"grandmothers|grandfathers|grandmother|grandfather|"
    r"mothers|fathers|mother|father|sisters|brothers|sister|brother|"
    r"daughters|sons|daughter|son|wives|husbands|wife|husband|"
    r"spouses|spouse|parents|parent|uncles|uncle|aunts|aunt|"
    r"cousins|cousin|nieces|niece|nephews|nephew|"
    r"family\s+members|family\s+member)"
)
_LEADING_ROLE = rf"(?:(?:an?|the|her|his|their)\s+)?{_ROLE_PREFIX}\s+(?:named\s+)?"
_TRAILING_ROLE = (
    rf"\s*,\s*(?:(?:an?|the)\s+)?(?:defendant(?:'s|’s)\s+)?{_ROLE_PREFIX}\b"
)
_FAMILY = (
    r"grandmothers|grandfathers|grandmother|grandfather|mothers|fathers|"
    r"mother|father|sisters|brothers|sister|brother|daughters|sons|daughter|"
    r"son|wives|husbands|wife|husband|spouses|spouse|parents|parent|uncles|"
    r"uncle|aunts|aunt|cousins|cousin|nieces|niece|nephews|nephew|"
    r"family\s+members|family\s+member"
)
_NAME_STOP = frozenset(
    {
        "the",
        "court",
        "state",
        "county",
        "police",
        "officer",
        "judge",
        "justice",
        "united",
        "states",
        "district",
        "supreme",
        "department",
        "affidavit",
        "ruling",
        "people",
        "defendant",
        "plaintiff",
        "appellee",
        "appellant",
    }
)
_COMMAND_MARKERS = (
    "ignore previous instructions",
    "</data>",
    "<data>",
    "<system",
    "</system>",
    "</untrusted_source_",
    "<untrusted_source_",
    "exfiltrate",
    "insert a confession fact",
    "anonymization_status",
    "hedging_required",
    "source_type=",
    "anonymized_by",
    "anonymized_at",
)
_LEAK_MARKERS = (
    "ignore previous instructions",
    "</data>",
    "<data>",
    "<system",
    "</system>",
    "</untrusted_source_",
    "<untrusted_source_",
    "exfiltrate",
    "insert a confession fact",
)

def _ci(expr: str) -> str:
    """Case-fold a role phrase without letting the flag swallow the name."""

    return f"(?i:{expr})"


def _detector(role: str, pattern: str) -> tuple[str, re.Pattern[str]]:
    return role, re.compile(pattern)


_ALT_LEAD = _ci(
    r"(?:cleared\s+alternate\s+suspect|unconvicted\s+suspect|"
    r"alternate\s+suspect|cleared\s+suspect)\s+(?:named\s+)?"
)
_WITNESS_LEAD = _ci(r"(?:an?\s+)?(?:eyewitnesses|eyewitness|witnesses|witness)\s+(?:named\s+)?")
_WITNESS_TRAIL = _ci(r"(?:an?\s+)?(?:eyewitness|witness)")
_NEIGHBOR_LEAD = _ci(r"(?:neighbours|neighbour|neighbors|neighbor)\s+(?:named\s+)?")
_NEIGHBOR_TRAIL = _ci(r"(?:an?\s+)?(?:neighbour|neighbor)")
_COWORKER_LEAD = _ci(
    r"(?:co-workers|coworkers|co-worker|coworker|colleagues|colleague)\s+(?:named\s+)?"
)
_COWORKER_TRAIL = _ci(r"(?:an?\s+)?(?:co-worker|coworker|colleague)")
_FAMILY_LEAD = _ci(
    r"(?:(?:an?|the|her|his|their)\s+)?(?:defendant(?:'s|’s)\s+)?(?:"
    + _FAMILY
    + r")\s+(?:named\s+)?"
)
_FAMILY_TRAIL = _ci(
    r"(?:(?:an?|the)\s+)?(?:defendant(?:'s|’s)\s+)?(?:" + _FAMILY + r")"
)

_DETECTORS: tuple[tuple[str, re.Pattern[str]], ...] = (
    _detector("alternate_suspect", rf"\b{_ALT_LEAD}({_NAME})\b"),
    _detector("witness", rf"\b{_WITNESS_LEAD}({_NAME})\b"),
    _detector("witness", rf"\b({_NAME})\s*,\s*{_WITNESS_TRAIL}\b"),
    _detector("neighbor", rf"\b{_NEIGHBOR_LEAD}({_NAME})\b"),
    _detector("neighbor", rf"\b({_NAME})\s*,\s*{_NEIGHBOR_TRAIL}\b"),
    _detector("coworker", rf"\b{_COWORKER_LEAD}({_NAME})\b"),
    _detector("coworker", rf"\b({_NAME})\s*,\s*{_COWORKER_TRAIL}\b"),
    _detector("family", rf"\b{_FAMILY_LEAD}({_NAME})\b"),
    _detector("family", rf"\b({_NAME})\s*,\s*{_FAMILY_TRAIL}\b"),
)


class FactExtractionError(ValueError):
    """The filing could not be turned into a reviewable fact ledger."""


@dataclass(frozen=True)
class FactExtraction:
    """Data returned by the extractor. Nothing here is written to SQLite."""

    prompt_contract_id: str
    nonce: str
    wrapped_source: str
    ledger: TemporalFactLedger
    anonymization_status: str
    anonymization_artifact_sha256: str
    alias_map: dict[str, str]
    tools_enabled: bool = False
    writes_database: bool = False

    def __post_init__(self) -> None:
        if self.prompt_contract_id != PROMPT_CONTRACT_ID:
            raise FactExtractionError("unexpected prompt contract")
        if self.anonymization_status != "IN_REVIEW":
            raise FactExtractionError("anonymization_status must be IN_REVIEW")
        if self.tools_enabled or self.writes_database:
            raise FactExtractionError("extractor cannot enable tools or database writes")
        if not re.fullmatch(r"[0-9a-f]{64}", self.anonymization_artifact_sha256):
            raise FactExtractionError("anonymization artifact hash must be sha256")
        alias_map = dict(self.alias_map)
        object.__setattr__(self, "alias_map", alias_map)
        if alias_map_sha256(alias_map) != self.anonymization_artifact_sha256:
            raise FactExtractionError("artifact hash does not match the alias map")
        opener = f"<untrusted_source_{self.nonce}>"
        closer = f"</untrusted_source_{self.nonce}>"
        if not (self.wrapped_source.startswith(opener) and self.wrapped_source.endswith(closer)):
            raise FactExtractionError("wrapped source is missing its nonce tag")

    def case_patch(self) -> dict[str, str]:
        """Fields a later writer may store. `APPROVED` is never included."""

        return {
            "anonymization_status": self.anonymization_status,
            "anonymization_artifact_sha256": self.anonymization_artifact_sha256,
        }


def wrap_untrusted_source(source_text: str, *, nonce: str | None = None) -> tuple[str, str]:
    """Escape delimiter breakouts and wrap the filing in a random nonce tag."""

    if nonce is None:
        nonce = secrets.token_hex(2)
    if _NONCE_RE.fullmatch(nonce) is None:
        raise FactExtractionError("nonce must be four lowercase hex characters")
    escaped = (
        source_text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    tag = f"untrusted_source_{nonce}"
    return nonce, f"<{tag}>{escaped}</{tag}>"


def alias_map_sha256(alias_map: Mapping[str, str]) -> str:
    """SHA-256 of the canonical JSON alias map (sorted keys, compact separators)."""

    payload = json.dumps(
        {name: alias_map[name] for name in sorted(alias_map)},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def source_type_from_document(document: Mapping[str, Any]) -> str:
    """Map a `primary_documents` row onto a fact-ledger `source_type`.

    `doc_type` wins when both columns are present. Model text is not read.
    """

    doc_type = document.get("doc_type")
    if isinstance(doc_type, str) and doc_type in _DOC_TYPE_TO_SOURCE:
        return _DOC_TYPE_TO_SOURCE[doc_type]
    source_type = document.get("source_type")
    if isinstance(source_type, str) and source_type in _SOURCE_TYPES:
        return source_type
    raise FactExtractionError(
        "cited document row has no fact-ledger source tier "
        "(court_ruling, police_affidavit, or news_text_only)"
    )


class FactExtractor:
    """`evidence-ledger-extractor@3` without tools or database privileges."""

    def __init__(self) -> None:
        if TOOLS_ENABLED or WRITES_DATABASE:
            raise FactExtractionError("tool-less extractor cannot enable tools or database writes")

    def extract(
        self,
        *,
        case: Mapping[str, Any],
        document: Mapping[str, Any],
        source_text: str,
        model_text: str | None = None,
        nonce: str | None = None,
    ) -> FactExtraction:
        case_id = _require_entity(case.get("case_id"), "case_id")
        defendant_name = _require_text(case.get("defendant_name"), "defendant_name")
        _require_standing(case.get("disposition_status"))
        _require_not_started(case.get("anonymization_status", "NOT_STARTED"))
        doc_id = _require_entity(document.get("doc_id"), "doc_id")
        doc_case = document.get("case_id")
        if doc_case is not None and str(doc_case) != case_id:
            raise FactExtractionError("cited document case_id does not match the case record")
        source_type = source_type_from_document(document)
        citation_default = _citation_default(document, doc_id)
        incident_year = _incident_year(case.get("incident_year"))

        issued_nonce, wrapped_source = wrap_untrusted_source(source_text, nonce=nonce)
        stripped_source = strip_injected_commands(source_text)
        candidates = _candidate_facts(
            source_text=source_text,
            model_text=model_text,
            incident_year=incident_year,
        )
        alias_map = build_alias_map(
            _detection_corpus(stripped_source, candidates),
            defendant_name=defendant_name,
        )
        facts = _materialize_facts(
            candidates,
            case_id=case_id,
            doc_id=doc_id,
            source_type=source_type,
            citation_default=citation_default,
            alias_map=alias_map,
            defendant_name=defendant_name,
            incident_year=incident_year,
        )
        if not facts:
            raise FactExtractionError("no documentary facts remained after command stripping")
        _reject_command_leaks(facts)
        ledger = TemporalFactLedger(
            contract_version=CONTRACT_VERSION,
            case_id=case_id,
            facts=facts,
        )
        digest = alias_map_sha256(alias_map)
        return FactExtraction(
            prompt_contract_id=PROMPT_CONTRACT_ID,
            nonce=issued_nonce,
            wrapped_source=wrapped_source,
            ledger=ledger,
            anonymization_status="IN_REVIEW",
            anonymization_artifact_sha256=digest,
            alias_map=alias_map,
            tools_enabled=False,
            writes_database=False,
        )


def extract_facts(
    *,
    case: Mapping[str, Any],
    document: Mapping[str, Any],
    source_text: str,
    model_text: str | None = None,
    nonce: str | None = None,
) -> FactExtraction:
    """Extract one ledger. See `FactExtractor.extract`."""

    return FactExtractor().extract(
        case=case,
        document=document,
        source_text=source_text,
        model_text=model_text,
        nonce=nonce,
    )


def strip_injected_commands(text: str) -> str:
    """Drop injected instructions. Documentary sentences before them remain.

    Line breaks stay intact so a `FACT` header is not glued to its body.
    """

    cleaned = _TAG_RE.sub(" ", text)
    kept_lines: list[str] = []
    for line in cleaned.splitlines():
        kept_sentences: list[str] = []
        for sentence in re.split(r"(?<=[.!?])\s+", line):
            salvaged = _sweep_phrases(_salvage_sentence(sentence))
            if _has_words(salvaged) and not _is_command_sentence(salvaged):
                kept_sentences.append(salvaged.strip())
        if kept_sentences:
            kept_lines.append(" ".join(kept_sentences))
    return "\n".join(kept_lines).strip()


def build_alias_map(text: str, *, defendant_name: str) -> dict[str, str]:
    """Map unconvicted third-party names to role aliases, skipping the defendant."""

    mentions: list[tuple[int, str, str]] = []
    for role, pattern in _DETECTORS:
        for match in pattern.finditer(text):
            mentions.append((match.start(1), role, match.group(1).strip()))
    mentions.sort(key=lambda item: item[0])

    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _start, role, name in mentions:
        key = name.casefold()
        if key in seen or _is_defendant(name, defendant_name) or _stopped(name):
            continue
        seen.add(key)
        ordered.append((name, role))

    counts = {"witness": 0, "neighbor": 0, "coworker": 0, "family": 0, "alternate_suspect": 0}
    alias_map: dict[str, str] = {}
    for name, role in ordered:
        alias_map[name] = _alias_for(role, counts[role])
        counts[role] += 1
    return alias_map


def scrub_text(text: str, alias_map: Mapping[str, str], defendant_name: str) -> str:
    """Replace third-party names. The case-record defendant is restored intact."""

    if not text:
        return text
    sentinel = "\ue000DEFENDANT\ue000"
    protected = text
    if defendant_name:
        protected = re.sub(re.escape(defendant_name), sentinel, protected, flags=re.IGNORECASE)
    for name in sorted(alias_map, key=len, reverse=True):
        pattern = re.compile(
            rf"\b(?:{_LEADING_ROLE})?{re.escape(name)}\b(?:{_TRAILING_ROLE})?",
            re.IGNORECASE,
        )
        alias = alias_map[name]
        protected = pattern.sub(lambda _match, alias=alias: alias, protected)
    restored = protected.replace(sentinel, defendant_name)
    return re.sub(r"[ \t]{2,}", " ", restored).strip()


def _alias_for(role: str, index: int) -> str:
    letter = _LETTERS[index] if index < len(_LETTERS) else str(index + 1)
    if role == "witness":
        return f"Witness {letter}"
    if role == "neighbor":
        return f"Neighbor {letter}"
    if role == "coworker":
        return "a coworker"
    if role == "family":
        return f"Family member {letter}"
    if role == "alternate_suspect":
        return f"Alternate suspect {letter}"
    raise FactExtractionError(f"unknown third-party role: {role}")


def _candidate_facts(
    *,
    source_text: str,
    model_text: str | None,
    incident_year: int | None,
) -> list[dict[str, Any]]:
    if model_text is not None and model_text.strip():
        from_model = _facts_from_untrusted_text(model_text, incident_year=incident_year)
        if from_model:
            return from_model
    return _facts_from_untrusted_text(source_text, incident_year=incident_year)


def _facts_from_untrusted_text(text: str, *, incident_year: int | None) -> list[dict[str, Any]]:
    decoded = _decode_model_json(text)
    if decoded is not None:
        raw_facts = _facts_from_json(decoded)
        if raw_facts:
            return raw_facts
    blocked = _parse_fact_blocks(text)
    if blocked:
        return blocked
    prose_source = strip_injected_commands(text if blocked is None else _without_fact_headers(text))
    return _parse_prose_facts(prose_source, incident_year=incident_year)


def _decode_model_json(text: str) -> Any | None:
    starts = [index for index in (text.find("{"), text.find("[")) if index >= 0]
    if not starts:
        return None
    decoder = json.JSONDecoder()
    try:
        payload, _end = decoder.raw_decode(text[min(starts) :])
    except json.JSONDecodeError:
        return None
    return payload


def _facts_from_json(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        raw_facts = payload
    elif isinstance(payload, dict):
        nested = payload.get("facts")
        if isinstance(nested, list):
            raw_facts = nested
        elif "event_summary" in payload:
            raw_facts = [payload]
        else:
            raw_facts = []
    else:
        return []
    facts: list[dict[str, Any]] = []
    for item in raw_facts:
        if isinstance(item, dict):
            facts.append(dict(item))
    return facts


def _parse_fact_blocks(text: str) -> list[dict[str, Any]] | None:
    """Parse `FACT` blocks from raw text. `None` means the text has no blocks."""

    if re.search(r"^FACT\b", text, re.MULTILINE) is None:
        return None
    facts: list[dict[str, Any]] = []
    for part in _FACT_SPLIT.split(text):
        stripped = part.strip()
        if not stripped.startswith("FACT"):
            continue
        lines = stripped.splitlines()
        fields = _parse_fact_header(lines[0])
        body = strip_injected_commands("\n".join(lines[1:]))
        if not _has_words(body):
            continue
        fields["event_summary"] = " ".join(body.split())
        facts.append(fields)
    return facts


def _parse_fact_header(header: str) -> dict[str, Any]:
    try:
        tokens = shlex.split(header, posix=True)
    except ValueError as exc:
        raise FactExtractionError("unreadable FACT header") from exc
    raw: dict[str, str] = {}
    for token in tokens[1:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        raw[key] = value
    fields: dict[str, Any] = {}
    if "id" in raw:
        fields["fact_id"] = raw["id"]
    elif "fact_id" in raw:
        fields["fact_id"] = raw["fact_id"]
    if "when" in raw:
        fields["datetime_iso"] = raw["when"]
    elif "datetime_iso" in raw:
        fields["datetime_iso"] = raw["datetime_iso"]
    if "where" in raw:
        fields["location_text"] = raw["where"]
    elif "location_text" in raw:
        fields["location_text"] = raw["location_text"]
    if "cite" in raw:
        fields["citation_locator"] = raw["cite"]
    elif "citation_locator" in raw:
        fields["citation_locator"] = raw["citation_locator"]
    clues = raw.get("clues")
    if clues:
        fields["physical_clues_json"] = [part.strip() for part in clues.split("|") if part.strip()]
    return fields


def _parse_prose_facts(text: str, *, incident_year: int | None) -> list[dict[str, Any]]:
    found = _ISO_SEARCH.search(text)
    default_dt = found.group(0) if found else _year_datetime(incident_year)
    facts: list[dict[str, Any]] = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        summary = " ".join(sentence.split())
        if not _has_words(summary):
            continue
        stamp = _ISO_SEARCH.search(summary)
        facts.append(
            {
                "event_summary": summary,
                "datetime_iso": stamp.group(0) if stamp else default_dt,
                "location_text": "unspecified location",
            }
        )
    return facts


def _without_fact_headers(text: str) -> str:
    kept = [
        line
        for line in text.splitlines()
        if not line.lstrip().startswith("FACT ") and line.strip() != "FACT"
    ]
    return "\n".join(kept)


def _materialize_facts(
    candidates: Sequence[Mapping[str, Any]],
    *,
    case_id: str,
    doc_id: str,
    source_type: str,
    citation_default: str,
    alias_map: Mapping[str, str],
    defendant_name: str,
    incident_year: int | None,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for index, raw in enumerate(candidates, start=1):
        summary = scrub_text(
            strip_injected_commands(str(raw.get("event_summary") or "")),
            alias_map,
            defendant_name,
        )
        summary = " ".join(summary.split())
        if not _has_words(summary) or _is_command_sentence(summary):
            continue
        when = str(raw.get("datetime_iso") or _year_datetime(incident_year) or "")
        if _ISO_DT.fullmatch(when) is None:
            raise FactExtractionError("datetime_iso must be timezone-aware ISO-8601")
        location = scrub_text(
            strip_injected_commands(str(raw.get("location_text") or "unspecified location")),
            alias_map,
            defendant_name,
        ) or "unspecified location"
        citation = scrub_text(
            strip_injected_commands(str(raw.get("citation_locator") or citation_default)),
            alias_map,
            defendant_name,
        ) or citation_default
        clues = [
            scrubbed
            for clue in _clue_list(raw.get("physical_clues_json"))
            if (scrubbed := scrub_text(strip_injected_commands(clue), alias_map, defendant_name))
        ]
        fact_id = _entity_or_default(raw.get("fact_id"), f"fact_{index}")
        facts.append(
            {
                "fact_id": fact_id,
                "case_id": case_id,
                "datetime_iso": when,
                "event_summary": summary,
                "physical_clues_json": clues,
                "location_text": location,
                "source_type": source_type,
                "source_doc_id": doc_id,
                "citation_locator": citation,
                "hedging_required": _hedging(source_type, raw.get("hedging_required")),
                "contradicts_json": _entity_list(raw.get("contradicts_json")),
            }
        )
    return facts


def _detection_corpus(source_text: str, candidates: Sequence[Mapping[str, Any]]) -> str:
    parts = [source_text]
    for raw in candidates:
        parts.append(strip_injected_commands(str(raw.get("event_summary") or "")))
        parts.append(strip_injected_commands(str(raw.get("location_text") or "")))
        parts.append(strip_injected_commands(str(raw.get("citation_locator") or "")))
        for clue in _clue_list(raw.get("physical_clues_json")):
            parts.append(strip_injected_commands(clue))
    return "\n".join(parts)


def _hedging(source_type: str, requested: Any) -> bool:
    if source_type == "news_report":
        return True
    if isinstance(requested, bool):
        return requested
    if requested in (0, 1):
        return bool(requested)
    return False


def _clue_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split("|") if part.strip()]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _entity_list(value: Any) -> list[str]:
    kept: list[str] = []
    for item in _clue_list(value):
        token = re.sub(r"[^A-Za-z0-9_-]", "", item)
        if token and _ENTITY_RE.fullmatch(token):
            kept.append(token)
    return kept


def _entity_or_default(value: Any, default: str) -> str:
    if value is None:
        return default
    token = re.sub(r"[^A-Za-z0-9_-]", "_", str(value)).strip("_")
    if token and _ENTITY_RE.fullmatch(token) and len(token) <= 128:
        return token
    return default


def _citation_default(document: Mapping[str, Any], doc_id: str) -> str:
    citation = document.get("citation_locator")
    if isinstance(citation, str) and citation.strip():
        return citation.strip()
    return doc_id


def _incident_year(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        year = int(value)
    except (TypeError, ValueError) as exc:
        raise FactExtractionError("incident_year must be an integer") from exc
    if year < 1800 or year > 2100:
        raise FactExtractionError("incident_year is outside the supported range")
    return year


def _year_datetime(year: int | None) -> str | None:
    if year is None:
        return None
    return f"{year:04d}-01-01T00:00:00Z"


def _require_standing(disposition: Any) -> None:
    if disposition is None or disposition == "":
        return
    status = str(disposition)
    if status not in _STANDING_DISPOSITIONS:
        raise FactExtractionError(
            "disposition_status must be AFFIRMED or STANDING_CONVICTION to extract a ledger"
        )


def _require_not_started(status: Any) -> None:
    if str(status) != "NOT_STARTED":
        raise FactExtractionError(
            "anonymization_status moves from NOT_STARTED to IN_REVIEW only and is never set to APPROVED"
        )


def _require_entity(value: Any, label: str) -> str:
    if not isinstance(value, str) or _ENTITY_RE.fullmatch(value) is None or len(value) > 128:
        raise FactExtractionError(f"{label} must be a non-empty entity id")
    return value


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FactExtractionError(f"{label} is required")
    return value.strip()


def _salvage_sentence(sentence: str) -> str:
    lowered = sentence.casefold()
    cut = len(sentence)
    for marker in _COMMAND_MARKERS:
        index = lowered.find(marker)
        if index != -1:
            cut = min(cut, index)
    if cut == len(sentence):
        return sentence.strip()
    return sentence[:cut].strip(" \t-;:,")


def _sweep_phrases(text: str) -> str:
    cleaned = text
    for marker in _COMMAND_MARKERS:
        cleaned = re.sub(re.escape(marker), " ", cleaned, flags=re.IGNORECASE)
    return re.sub(r"[ \t]{2,}", " ", cleaned).strip()


def _is_command_sentence(sentence: str) -> bool:
    lowered = sentence.casefold()
    return any(marker in lowered for marker in _COMMAND_MARKERS)


def _has_words(text: str) -> bool:
    return re.search(r"[A-Za-z]{3,}", text) is not None


def _is_defendant(name: str, defendant_name: str) -> bool:
    return name.casefold() == defendant_name.casefold()


def _stopped(name: str) -> bool:
    return any(part.casefold() in _NAME_STOP for part in name.split())


def _reject_command_leaks(facts: Sequence[Mapping[str, Any]]) -> None:
    blob = json.dumps(list(facts), ensure_ascii=False).casefold()
    for marker in _LEAK_MARKERS:
        if marker in blob:
            raise FactExtractionError("injected command leaked into extracted facts")
