"""Primary-record and appellate disposition gate.

A documentary case may proceed only when injected CourtListener, state DOC,
and .gov lookups corroborate a standing conviction. Passing dispositions are
``AFFIRMED`` and ``STANDING_CONVICTION``. ``REVERSED``, ``VACATED``,
``ACQUITTED``, and ``PENDING`` are hard kills, as are fictional NoSleep-style
leads with no primary record.

This module does not fetch records and does not open sockets. Callers inject
the three lookups. It does not write ``schema/pipeline.sql``. The pass rule
matches ``trg_case_disposition_guard_insert`` and
``trg_case_disposition_guard_update``: ``conviction_confirmed`` is true only
when ``disposition_status`` is ``AFFIRMED`` or ``STANDING_CONVICTION``.

Count split: when a homicide count is affirmed and another count is reversed,
the gate passes as ``STANDING_CONVICTION`` only if the DOC lookup still shows
that homicide conviction. A vacated conviction, or a remand for a new trial,
is a hard kill even if one count line still says affirmed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

PASSING_DISPOSITIONS = frozenset({"AFFIRMED", "STANDING_CONVICTION"})
KILL_DISPOSITIONS = frozenset({"REVERSED", "VACATED", "ACQUITTED", "PENDING"})
KNOWN_DISPOSITIONS = PASSING_DISPOSITIONS | KILL_DISPOSITIONS
_KILL_ORDER = ("VACATED", "REVERSED", "ACQUITTED", "PENDING")
_HOMICIDE_WORDS = frozenset({"homicide", "murder", "manslaughter"})
_FICTION_TOKENS = ("nosleep", "no-sleep", "no_sleep", "creepypasta")
_FICTION_LABELS = frozenset({"fiction", "nosleep", "creepypasta", "r/nosleep"})
_REASON_RANK = {
    "WHOLE_CONVICTION_VACATED": 0,
    "REMANDED_FOR_NEW_TRIAL": 1,
    "APPELLATE_VACATED": 2,
    "APPELLATE_REVERSED": 3,
    "APPELLATE_ACQUITTED": 4,
    "APPELLATE_PENDING": 5,
    "DISPOSITION_CONFLICT": 6,
    "MIXED_DISPOSITION_NOT_HOMICIDE": 7,
    "UNKNOWN_DISPOSITION": 8,
}

Verdict = Literal["PASS", "KILL"]
Record = Mapping[str, Any]
RecordLookup = Callable[
    [Sequence[str], int, Sequence[str]],
    Sequence[Record] | Record | None,
]


@dataclass(frozen=True, slots=True)
class GateDecision:
    """Result of one primary-record check.

    ``passed`` is the only proceed bit. A killed case keeps
    ``conviction_confirmed`` false. ``disposition_status`` on a kill is either
    a blocking appellate status or ``None``; it is never a passing status.
    ``primary_record_verified`` means all three real sources matched the
    name, year, and docket. It is not permission to script the case.
    """

    verdict: Verdict
    disposition_status: str | None
    conviction_confirmed: bool
    primary_record_verified: bool
    reason: str
    verification_source: str
    detail: str

    @property
    def passed(self) -> bool:
        return self.verdict == "PASS"

    @property
    def killed(self) -> bool:
        return self.verdict == "KILL"


@dataclass(frozen=True, slots=True)
class _Query:
    names: tuple[str, ...]
    name_keys: frozenset[str]
    year: int
    dockets: tuple[str, ...]
    docket_keys: frozenset[str]
    nosleep: bool


@dataclass(frozen=True, slots=True)
class _Count:
    number: int | None
    charge: str
    disposition: str


@dataclass(frozen=True, slots=True)
class _Classified:
    kind: Literal["hard", "partial", "clean"]
    disposition: str | None
    reason: str


def _kill(
    reason: str,
    detail: str,
    *,
    disposition: str | None = None,
    verified: bool = False,
    source: str = "unverified",
) -> GateDecision:
    if disposition in PASSING_DISPOSITIONS:
        disposition = None
        reason = "UNKNOWN_DISPOSITION"
        detail = "Refusing to label a blocked case as a standing conviction."
        verified = False
    return GateDecision(
        verdict="KILL",
        disposition_status=disposition,
        conviction_confirmed=False,
        primary_record_verified=verified,
        reason=reason,
        verification_source=source,
        detail=detail,
    )


def _pass(disposition: str, detail: str) -> GateDecision:
    if disposition not in PASSING_DISPOSITIONS:
        return _kill(
            "UNKNOWN_DISPOSITION",
            "Refusing a pass that is not AFFIRMED or STANDING_CONVICTION.",
        )
    return GateDecision(
        verdict="PASS",
        disposition_status=disposition,
        conviction_confirmed=True,
        primary_record_verified=True,
        reason=f"PASS_{disposition}",
        verification_source="courtlistener+state_doc+gov",
        detail=detail,
    )


def _norm_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _norm_docket(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _host(value: str) -> str:
    text = value.strip().casefold()
    if "://" in text:
        text = text.split("://", 1)[1]
    if text.startswith("//"):
        text = text[2:]
    host = text.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    if "@" in host:
        host = host.rsplit("@", 1)[1]
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    else:
        host = host.split(":", 1)[0]
    return host.strip(".")


def _is_gov_host(host: str) -> bool:
    return host.endswith(".gov") and host not in {".gov", "gov"} and ".." not in host


def _is_homicide(charge: str) -> bool:
    cleaned = "".join(ch if ch.isalnum() else " " for ch in charge.casefold())
    return bool(set(cleaned.split()) & _HOMICIDE_WORDS)


def _blob(record: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "origin",
        "source",
        "source_domain",
        "source_url",
        "source_type",
        "record_kind",
        "url",
        "domain",
    ):
        value = record.get(key)
        if isinstance(value, str):
            parts.append(value)
    return " ".join(parts).casefold()


def _is_fictional(record: Mapping[str, Any]) -> bool:
    if record.get("fictional") is True:
        return True
    source_type = str(record.get("source_type") or "").casefold()
    origin = str(record.get("origin") or "").casefold()
    if source_type in _FICTION_LABELS or origin in _FICTION_LABELS:
        return True
    blob = _blob(record)
    return any(token in blob for token in _FICTION_TOKENS)


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _record_names(record: Mapping[str, Any]) -> set[str]:
    explicit: list[str] = []
    explicit.extend(_string_list(record.get("suspect_names")))
    explicit.extend(_string_list(record.get("defendant_names")))
    defendant = record.get("defendant_name")
    if isinstance(defendant, str) and defendant.strip():
        explicit.append(defendant)
    if explicit:
        return {_norm_name(item) for item in explicit if _norm_name(item)}
    case_name = record.get("case_name")
    if not isinstance(case_name, str):
        return set()
    tokens = {
        token
        for token in _norm_name(case_name).replace(".", " ").split()
        if len(token) > 1 and token not in {"vs", "v", "state", "people", "commonwealth"}
    }
    full = _norm_name(case_name)
    if full:
        tokens.add(full)
    return tokens


def _record_dockets(record: Mapping[str, Any]) -> set[str]:
    raw: list[str] = []
    for key in ("docket_id", "docket_number"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            raw.append(value)
    raw.extend(_string_list(record.get("docket_ids")))
    return {_norm_docket(item) for item in raw if _norm_docket(item)}


def _record_year(record: Mapping[str, Any]) -> int | None:
    for key in ("incident_year", "year"):
        value = record.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
    return None


def _disposition_of(record: Mapping[str, Any]) -> str | None:
    for key in ("disposition", "disposition_status"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _gov_hosts(record: Mapping[str, Any]) -> list[str]:
    hosts: list[str] = []
    for key in ("source_domain", "domain", "source_url", "url"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            host = _host(value)
            if host:
                hosts.append(host)
    return hosts


def _is_gov_record(record: Mapping[str, Any]) -> bool:
    return any(_is_gov_host(host) for host in _gov_hosts(record))


def _matches(record: Mapping[str, Any], query: _Query) -> bool:
    if _record_year(record) != query.year:
        return False
    if not query.name_keys <= _record_names(record):
        return False
    return query.docket_keys <= _record_dockets(record)


def _as_records(value: object) -> list[Record]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("record lookup must return a sequence of records")
    records: list[Record] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise TypeError("each record must be a mapping")
        records.append(item)
    return records


def _parse_query(
    suspect_names: object,
    incident_year: object,
    docket_ids: object,
) -> _Query | GateDecision:
    if isinstance(suspect_names, (str, bytes)) or not isinstance(suspect_names, Sequence):
        return _kill("INVALID_QUERY", "suspect_names must be a sequence of names.")
    if isinstance(docket_ids, (str, bytes)) or not isinstance(docket_ids, Sequence):
        return _kill("INVALID_QUERY", "docket_ids must be a sequence of docket ids.")
    if isinstance(incident_year, bool) or not isinstance(incident_year, int):
        return _kill("INVALID_QUERY", "incident_year must be an integer year.")
    if incident_year < 1 or incident_year > 9999:
        return _kill("INVALID_QUERY", "incident_year is outside the accepted range.")
    names = tuple(str(name).strip() for name in suspect_names)
    dockets = tuple(str(docket).strip() for docket in docket_ids)
    if not names or any(not name for name in names):
        return _kill("INVALID_QUERY", "At least one suspect name is required.")
    if not dockets or any(not docket for docket in dockets):
        return _kill("INVALID_QUERY", "At least one docket id is required.")
    name_keys = frozenset(_norm_name(name) for name in names)
    docket_keys = frozenset(_norm_docket(docket) for docket in dockets)
    if "" in name_keys or "" in docket_keys:
        return _kill("INVALID_QUERY", "Names and docket ids must contain letters or digits.")
    blob = " ".join((*names, *dockets)).casefold()
    return _Query(
        names=names,
        name_keys=name_keys,
        year=incident_year,
        dockets=dockets,
        docket_keys=docket_keys,
        nosleep=any(token in blob for token in _FICTION_TOKENS),
    )


def _counts(record: Mapping[str, Any]) -> list[_Count]:
    raw = record.get("counts")
    if raw is None:
        return []
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TypeError("counts must be a sequence")
    parsed: list[_Count] = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise TypeError("each count must be a mapping")
        number = item.get("count", item.get("count_number"))
        number_out = number if isinstance(number, int) and not isinstance(number, bool) else None
        charge = item.get("charge", item.get("offense", ""))
        disposition = item.get("disposition", item.get("disposition_status"))
        if isinstance(disposition, str) and disposition.strip().upper() in KNOWN_DISPOSITIONS:
            label = disposition.strip().upper()
        else:
            label = "UNKNOWN"
        parsed.append(_Count(number_out, str(charge), label))
    return parsed


def _worst_disposition(labels: set[str]) -> str:
    for status in _KILL_ORDER:
        if status in labels:
            return status
    return "PENDING"


def _prefer_kill(current: str | None, new: str) -> str:
    if current is None:
        return new
    if _KILL_ORDER.index(new) < _KILL_ORDER.index(current):
        return new
    return current


def _classify(record: Mapping[str, Any]) -> _Classified:
    remanded = record.get("remanded_for_new_trial") is True
    vacated_whole = record.get("whole_conviction_vacated") is True
    top = _disposition_of(record)
    counts = _counts(record)

    if vacated_whole:
        return _Classified("hard", "VACATED", "WHOLE_CONVICTION_VACATED")
    if remanded:
        status = top if top in KILL_DISPOSITIONS else "PENDING"
        return _Classified("hard", status, "REMANDED_FOR_NEW_TRIAL")
    if top == "VACATED":
        return _Classified("hard", "VACATED", "APPELLATE_VACATED")

    if any(count.disposition == "UNKNOWN" for count in counts):
        status = top if top in KILL_DISPOSITIONS else None
        return _Classified("hard", status, "UNKNOWN_DISPOSITION")

    if counts:
        homicide_pass = [
            count
            for count in counts
            if _is_homicide(count.charge) and count.disposition in PASSING_DISPOSITIONS
        ]
        homicide_kill = [
            count
            for count in counts
            if _is_homicide(count.charge) and count.disposition in KILL_DISPOSITIONS
        ]
        other_kill = [
            count
            for count in counts
            if not _is_homicide(count.charge) and count.disposition in KILL_DISPOSITIONS
        ]
        other_pass = [
            count
            for count in counts
            if not _is_homicide(count.charge) and count.disposition in PASSING_DISPOSITIONS
        ]
        if homicide_kill:
            status = _worst_disposition({count.disposition for count in homicide_kill})
            return _Classified("hard", status, f"APPELLATE_{status}")
        if top in {"ACQUITTED", "PENDING"}:
            return _Classified("hard", top, f"APPELLATE_{top}")
        if top == "REVERSED" and not homicide_pass:
            return _Classified("hard", "REVERSED", "APPELLATE_REVERSED")
        if homicide_pass and other_kill:
            return _Classified("partial", "STANDING_CONVICTION", "PARTIAL_HOMICIDE")
        if other_kill and other_pass and not homicide_pass:
            return _Classified("hard", None, "MIXED_DISPOSITION_NOT_HOMICIDE")
        if other_kill and not homicide_pass:
            status = _worst_disposition({count.disposition for count in other_kill})
            return _Classified("hard", status, f"APPELLATE_{status}")
        passing = homicide_pass + other_pass
        if not passing or (top in KILL_DISPOSITIONS and not other_kill):
            if top in KILL_DISPOSITIONS:
                return _Classified("hard", top, f"APPELLATE_{top}")
            return _Classified("hard", None, "UNKNOWN_DISPOSITION")
        if any(count.disposition == "STANDING_CONVICTION" for count in passing):
            return _Classified("clean", "STANDING_CONVICTION", "CLEAN")
        return _Classified("clean", "AFFIRMED", "CLEAN")

    if top in PASSING_DISPOSITIONS:
        return _Classified("clean", top, "CLEAN")
    if top in KILL_DISPOSITIONS:
        return _Classified("hard", top, f"APPELLATE_{top}")
    return _Classified("hard", None, "UNKNOWN_DISPOSITION")


def _charge_list(record: Mapping[str, Any]) -> list[str]:
    charges: list[str] = []
    for key in ("standing_charges", "convictions", "offenses"):
        charges.extend(_string_list(record.get(key)))
    offense = record.get("offense")
    if isinstance(offense, str) and offense.strip():
        charges.append(offense)
    return charges


def _doc_homicide_state(records: Sequence[Mapping[str, Any]]) -> Literal["shown", "conflict", "absent"]:
    shown = False
    denied = False
    for record in records:
        flag = record.get("homicide_conviction_standing")
        charge_hit = any(_is_homicide(charge) for charge in _charge_list(record))
        if flag is True or charge_hit:
            shown = True
        if flag is False or _disposition_of(record) in KILL_DISPOSITIONS:
            denied = True
    if shown and denied:
        return "conflict"
    if shown:
        return "shown"
    return "absent"


def _doc_standing(records: Sequence[Mapping[str, Any]]) -> tuple[bool, str | None]:
    positive = False
    kill_status: str | None = None
    explicit_false = False
    for record in records:
        disposition = _disposition_of(record)
        if disposition in KILL_DISPOSITIONS:
            kill_status = _prefer_kill(kill_status, disposition)
        if disposition in PASSING_DISPOSITIONS:
            positive = True
        if record.get("conviction_standing") is True or record.get("homicide_conviction_standing") is True:
            positive = True
        if record.get("conviction_standing") is False:
            explicit_false = True
        if _charge_list(record):
            positive = True
    if kill_status is not None or explicit_false:
        return False, kill_status
    return positive, None


def _gov_block(records: Sequence[Mapping[str, Any]]) -> str | None:
    """Return a kill disposition, ``UNKNOWN``, or ``None`` when .gov does not block."""

    status: str | None = None
    for record in records:
        disposition = _disposition_of(record)
        if disposition in KILL_DISPOSITIONS:
            status = _prefer_kill(status, disposition)
        elif disposition is not None and disposition not in PASSING_DISPOSITIONS:
            return "UNKNOWN"
    return status


def _source_label(*, court: bool, doc: bool, gov: bool) -> str:
    parts: list[str] = []
    if court:
        parts.append("courtlistener")
    if doc:
        parts.append("state_doc")
    if gov:
        parts.append("gov")
    return "+".join(parts) if parts else "unverified"


def _pick_hard(classified: Sequence[_Classified]) -> _Classified:
    hard = [item for item in classified if item.kind == "hard"]
    return min(hard, key=lambda item: _REASON_RANK.get(item.reason, 99))


def _aggregate_clean(classified: Sequence[_Classified]) -> str:
    clean = [item.disposition for item in classified if item.kind == "clean"]
    if "STANDING_CONVICTION" in clean:
        return "STANDING_CONVICTION"
    return "AFFIRMED"


class PrimaryRecordVerifier:
    """Check injected primary records and block anything short of a standing conviction.

    ``courtlistener``, ``doc``, and ``gov`` are called with
    ``(suspect_names, incident_year, docket_ids)``. They must return in-memory
    records. A record matches only when its names, incident year, and docket
    ids cover the query. ``.gov`` records must use a ``.gov`` host.
    """

    def __init__(
        self,
        *,
        courtlistener: RecordLookup,
        doc: RecordLookup,
        gov: RecordLookup,
    ) -> None:
        self._courtlistener = courtlistener
        self._doc = doc
        self._gov = gov

    def verify(
        self,
        suspect_names: Sequence[str],
        incident_year: int,
        docket_ids: Sequence[str],
    ) -> GateDecision:
        parsed = _parse_query(suspect_names, incident_year, docket_ids)
        if isinstance(parsed, GateDecision):
            return parsed
        court_records = _as_records(
            self._courtlistener(parsed.names, parsed.year, parsed.dockets)
        )
        doc_records = _as_records(self._doc(parsed.names, parsed.year, parsed.dockets))
        gov_records = _as_records(self._gov(parsed.names, parsed.year, parsed.dockets))
        return _decide(parsed, court_records, doc_records, gov_records)


def _matched(records: Sequence[Mapping[str, Any]], query: _Query, *, gov: bool) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    for record in records:
        if _is_fictional(record):
            continue
        if gov and not _is_gov_record(record):
            continue
        if _matches(record, query):
            found.append(record)
    return found


def _fiction_matches(records: Sequence[Mapping[str, Any]], query: _Query) -> bool:
    return any(_is_fictional(record) and _matches(record, query) for record in records)


def _decide(
    query: _Query,
    court_records: Sequence[Mapping[str, Any]],
    doc_records: Sequence[Mapping[str, Any]],
    gov_records: Sequence[Mapping[str, Any]],
) -> GateDecision:
    court = _matched(court_records, query, gov=False)
    doc = _matched(doc_records, query, gov=False)
    gov = _matched(gov_records, query, gov=True)
    fiction = _fiction_matches([*court_records, *doc_records, *gov_records], query)
    source = _source_label(court=bool(court), doc=bool(doc), gov=bool(gov))
    verified = bool(court and doc and gov)

    if not court:
        if fiction or (query.nosleep and not (doc or gov)):
            return _kill(
                "FICTIONAL_NOSLEEP",
                "NoSleep-style fiction has no primary court, DOC, or .gov record.",
                source=source,
            )
        if doc or gov:
            return _kill(
                "INCOMPLETE_CORROBORATION",
                "CourtListener did not return a matching primary opinion.",
                source=source,
            )
        return _kill(
            "NO_PRIMARY_RECORD",
            "No CourtListener, state DOC, and .gov record matches this name, year, and docket.",
        )

    classified = [_classify(record) for record in court]
    if any(item.kind == "hard" for item in classified):
        chosen = _pick_hard(classified)
        return _kill(
            chosen.reason,
            _hard_detail(chosen),
            disposition=chosen.disposition,
            verified=verified,
            source=source,
        )

    if any(item.kind == "partial" for item in classified):
        return _decide_partial(doc, gov, verified=verified, source=source)

    return _decide_clean(classified, doc, gov, verified=verified, source=source)


def _hard_detail(chosen: _Classified) -> str:
    if chosen.reason == "WHOLE_CONVICTION_VACATED":
        return "The whole conviction is vacated, so the case cannot proceed."
    if chosen.reason == "REMANDED_FOR_NEW_TRIAL":
        return "The conviction was remanded for a new trial, so it is not standing."
    if chosen.reason == "MIXED_DISPOSITION_NOT_HOMICIDE":
        return "Mixed count dispositions do not leave a standing homicide conviction."
    if chosen.reason == "UNKNOWN_DISPOSITION":
        return "The judicial disposition is missing or is not a known appellate status."
    status = chosen.disposition or "UNKNOWN"
    return f"Appellate disposition {status} blocks a standing conviction."


def _decide_partial(
    doc: Sequence[Mapping[str, Any]],
    gov: Sequence[Mapping[str, Any]],
    *,
    verified: bool,
    source: str,
) -> GateDecision:
    """Homicide count affirmed, another count reversed: DOC must still show homicide."""

    if not doc or not gov:
        return _kill(
            "INCOMPLETE_CORROBORATION",
            "A split appellate opinion needs both a state DOC record and a .gov release.",
            source=source,
        )
    block = _gov_block(gov)
    if block == "UNKNOWN":
        return _kill(
            "UNKNOWN_DISPOSITION",
            "The .gov release does not use a known disposition.",
            verified=verified,
            source=source,
        )
    if block is not None:
        return _kill(
            "DISPOSITION_CONFLICT",
            "The .gov release does not leave the conviction standing.",
            disposition=block,
            verified=verified,
            source=source,
        )
    homicide = _doc_homicide_state(doc)
    if homicide == "conflict":
        return _kill(
            "DISPOSITION_CONFLICT",
            "State DOC records disagree about the homicide conviction.",
            verified=verified,
            source=source,
        )
    if homicide != "shown":
        return _kill(
            "DOC_HOMICIDE_NOT_STANDING",
            "An affirmed homicide count with another count reversed needs the DOC record to still show the homicide conviction.",
            verified=verified,
            source=source,
        )
    return _pass(
        "STANDING_CONVICTION",
        "Homicide count remains affirmed and the state DOC record still shows that conviction.",
    )


def _decide_clean(
    classified: Sequence[_Classified],
    doc: Sequence[Mapping[str, Any]],
    gov: Sequence[Mapping[str, Any]],
    *,
    verified: bool,
    source: str,
) -> GateDecision:
    if not doc or not gov:
        return _kill(
            "INCOMPLETE_CORROBORATION",
            "A standing disposition must be corroborated by CourtListener, state DOC, and a .gov release.",
            source=source,
        )
    standing, kill_status = _doc_standing(doc)
    if kill_status is not None:
        return _kill(
            "DISPOSITION_CONFLICT",
            "State DOC does not leave the conviction standing.",
            disposition=kill_status,
            verified=verified,
            source=source,
        )
    if not standing:
        return _kill(
            "DOC_CONVICTION_NOT_STANDING",
            "State DOC does not show a standing conviction.",
            verified=verified,
            source=source,
        )
    block = _gov_block(gov)
    if block == "UNKNOWN":
        return _kill(
            "UNKNOWN_DISPOSITION",
            "The .gov release does not use a known disposition.",
            verified=verified,
            source=source,
        )
    if block is not None:
        return _kill(
            "DISPOSITION_CONFLICT",
            "The .gov release does not leave the conviction standing.",
            disposition=block,
            verified=verified,
            source=source,
        )
    disposition = _aggregate_clean(classified)
    if disposition == "STANDING_CONVICTION":
        detail = "CourtListener, state DOC, and a .gov release corroborate STANDING_CONVICTION."
    else:
        detail = "CourtListener, state DOC, and a .gov release corroborate AFFIRMED."
    return _pass(disposition, detail)
