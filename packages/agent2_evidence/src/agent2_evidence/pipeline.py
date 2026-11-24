"""Offline Agent 2 evidence integration pipeline.

Stage rules from Tasks 033–042 are encoded here as local pure functions.
Modules from other Agent 2 branches are not imported. Nothing opens a socket.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

EVIDENCE_AND_2K_LOCKED = "EVIDENCE_AND_2K_LOCKED"
REJECTED_LOW_TWIST_DENSITY = "REJECTED_LOW_TWIST_DENSITY"
PARKED_COURTLISTENER_QUOTA = "PARKED_COURTLISTENER_QUOTA"
ILLUSTRATIVE_DISCLAIMER = "ILLUSTRATIVE RECONSTRUCTION — NOT CRIME SCENE PHOTO"

COURTLISTENER_CALL_LIMIT = 62
MIN_TURNING_POINTS = 3
NEWS_DOC_TYPE = "news_text_only"

PASSING_DISPOSITIONS = frozenset({"AFFIRMED", "STANDING_CONVICTION"})
KILL_DISPOSITIONS = frozenset({"REVERSED", "VACATED", "ACQUITTED", "PENDING"})

SOURCE_RANK = {
    "court_ruling": 3,
    "police_affidavit": 2,
    "news_report": 1,
}

_MEDIA_TAGS = frozenset({"img", "video", "picture", "source", "audio"})
_BLOCK_TAGS = frozenset(
    {"p", "div", "br", "h1", "h2", "h3", "li", "tr", "blockquote", "section", "article"}
)
_DATA_BASE64_RE = re.compile(
    r"data:[^;\"'\s>]+;base64,[A-Za-z0-9+/=\s]+",
    re.IGNORECASE,
)
_NAME_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b")

Record = Mapping[str, Any]
RecordLookup = Callable[[Sequence[str], int, Sequence[str]], Sequence[Record] | Record | None]


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class GateDecision:
    passed: bool
    disposition_status: str | None
    reason: str
    detail: str


@dataclass(frozen=True, slots=True)
class NewsTextResult:
    doc_type: str
    text: str
    retained_media_bytes: int


@dataclass(frozen=True, slots=True)
class FactRow:
    fact_id: str
    event_summary: str
    source_type: str
    hedging_required: int
    disputed: bool = False
    winning_source: str | None = None


@dataclass(frozen=True, slots=True)
class TurningPointBeat:
    beat_id: str
    summary: str
    source_type: str


@dataclass(frozen=True, slots=True)
class SpatialAnchor:
    anchor_id: str
    grid_cell: str
    span_cols: float
    span_rows: float
    target_zoom: float
    lock_status: str
    still_asset_sha256: str
    is_illustrative_reconstruction: int


@dataclass(frozen=True, slots=True)
class HarvestState:
    calls_used: int
    parked: bool
    cached_doc_ids: tuple[str, ...]
    requested_calls: int


@dataclass(frozen=True, slots=True)
class PipelineOutcome:
    case_id: str
    conveyor_state: str
    gate: GateDecision | None
    anonymization_status: str
    anonymized_names: dict[str, str]
    news: NewsTextResult | None
    facts: tuple[FactRow, ...]
    turning_points: tuple[TurningPointBeat, ...]
    anchors: tuple[SpatialAnchor, ...]
    harvest: HarvestState | None
    stages: tuple[str, ...]
    failure_reason: str | None = None


def _as_records(value: object) -> list[Record]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError("record lookup must return a sequence of records")
    return [item for item in value if isinstance(item, Mapping)]


def _norm_docket(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _matches(record: Mapping[str, Any], names: Sequence[str], year: int, dockets: Sequence[str]) -> bool:
    record_year = record.get("incident_year", record.get("year"))
    if record_year != year:
        return False
    record_names = set()
    for key in ("suspect_names", "defendant_names"):
        raw = record.get(key)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
            record_names.update(str(item).casefold() for item in raw)
    defendant = record.get("defendant_name")
    if isinstance(defendant, str):
        record_names.add(defendant.casefold())
    wanted = {name.casefold() for name in names}
    if wanted and not wanted <= record_names:
        return False
    record_dockets: set[str] = set()
    for key in ("docket_id", "docket_number"):
        value = record.get(key)
        if isinstance(value, str):
            record_dockets.add(_norm_docket(value))
    raw_ids = record.get("docket_ids")
    if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, (str, bytes)):
        record_dockets.update(_norm_docket(str(item)) for item in raw_ids)
    wanted_dockets = {_norm_docket(item) for item in dockets}
    return wanted_dockets <= record_dockets


def _disposition(record: Mapping[str, Any]) -> str | None:
    for key in ("disposition", "disposition_status"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().upper()
    return None


def _is_gov(record: Mapping[str, Any]) -> bool:
    for key in ("source_domain", "domain", "source_url", "url"):
        value = record.get(key)
        if isinstance(value, str) and ".gov" in value.casefold():
            host = value.casefold().split("://")[-1].split("/")[0]
            return host.endswith(".gov")
    return False


def verify_disposition(
    suspect_names: Sequence[str],
    incident_year: int,
    docket_ids: Sequence[str],
    *,
    courtlistener: RecordLookup,
    doc: RecordLookup,
    gov: RecordLookup,
) -> GateDecision:
    """Primary-record gate: AFFIRMED passes; REVERSED and allies hard-kill."""
    court = [
        row
        for row in _as_records(courtlistener(suspect_names, incident_year, docket_ids))
        if _matches(row, suspect_names, incident_year, docket_ids)
    ]
    state_doc = [
        row
        for row in _as_records(doc(suspect_names, incident_year, docket_ids))
        if _matches(row, suspect_names, incident_year, docket_ids)
    ]
    gov_records = [
        row
        for row in _as_records(gov(suspect_names, incident_year, docket_ids))
        if _matches(row, suspect_names, incident_year, docket_ids) and _is_gov(row)
    ]
    if not court or not state_doc or not gov_records:
        return GateDecision(
            passed=False,
            disposition_status=None,
            reason="INCOMPLETE_CORROBORATION",
            detail="CourtListener, state DOC, and a .gov release must all match.",
        )
    for row in court:
        status = _disposition(row)
        if status in KILL_DISPOSITIONS:
            return GateDecision(
                passed=False,
                disposition_status=status,
                reason=f"APPELLATE_{status}",
                detail=f"Appellate disposition {status} blocks a standing conviction.",
            )
    top = _disposition(court[0]) or "AFFIRMED"
    if top not in PASSING_DISPOSITIONS:
        return GateDecision(
            passed=False,
            disposition_status=top,
            reason="UNKNOWN_DISPOSITION",
            detail="Disposition is not AFFIRMED or STANDING_CONVICTION.",
        )
    for row in state_doc:
        if row.get("conviction_standing") is False:
            return GateDecision(
                passed=False,
                disposition_status=_disposition(row),
                reason="DOC_CONVICTION_NOT_STANDING",
                detail="State DOC does not show a standing conviction.",
            )
    return GateDecision(
        passed=True,
        disposition_status=top,
        reason=f"PASS_{top}",
        detail="CourtListener, state DOC, and a .gov release corroborate the conviction.",
    )


class _NewsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_l = tag.lower()
        if tag_l in _MEDIA_TAGS:
            self._skip += 1
            return
        if self._skip:
            return
        if tag_l in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_l = tag.lower()
        if tag_l in _MEDIA_TAGS and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if tag_l in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        data = _DATA_BASE64_RE.sub("", data)
        self.parts.append(data)


def extract_news_text_only(html: str) -> NewsTextResult:
    sanitized = _DATA_BASE64_RE.sub("", html)
    parser = _NewsParser()
    parser.feed(sanitized)
    parser.close()
    lines = [" ".join(line.split()) for line in "".join(parser.parts).splitlines() if line.strip()]
    text = "\n".join(lines)
    payload = text.encode("utf-8")
    retained = 0
    lowered = text.lower()
    for needle in ("<img", "<video", "data:image", "base64,"):
        if needle in lowered:
            retained += len(needle)
    return NewsTextResult(doc_type=NEWS_DOC_TYPE, text=text, retained_media_bytes=retained)


def plan_courtlistener_harvest(
    *,
    calls_used: int,
    pending_calls: int,
    cached_doc_ids: Sequence[str],
    queue_doc_ids: Sequence[str],
) -> HarvestState:
    """Park harvest when the next batch would exceed the offline call budget."""
    limit = COURTLISTENER_CALL_LIMIT
    if calls_used + pending_calls > limit:
        return HarvestState(
            calls_used=calls_used,
            parked=True,
            cached_doc_ids=tuple(cached_doc_ids),
            requested_calls=pending_calls,
        )
    merged = tuple(dict.fromkeys([*cached_doc_ids, *queue_doc_ids]))
    return HarvestState(
        calls_used=calls_used + pending_calls,
        parked=False,
        cached_doc_ids=merged,
        requested_calls=pending_calls,
    )


def alias_unconvicted_third_parties(
    text: str,
    *,
    defendant_name: str,
    unconvicted_names: Sequence[str],
) -> tuple[str, dict[str, str]]:
    aliases: dict[str, str] = {}
    witness_n = 0
    neighbor_n = 0
    out = text
    defendant_key = defendant_name.casefold()
    for name in unconvicted_names:
        if name.casefold() == defendant_key:
            continue
        lowered = name.casefold()
        role = "witness" if "witness" in lowered or witness_n == 0 else "neighbor"
        if role == "witness":
            witness_n += 1
            alias = f"Witness {chr(ord('A') + witness_n - 1)}"
        else:
            neighbor_n += 1
            alias = f"Neighbor {chr(ord('A') + neighbor_n - 1)}"
        aliases[name] = alias
        out = re.sub(re.escape(name), alias, out)
    return out, aliases


def reconcile_conflicts(groups: Sequence[Mapping[str, Any]]) -> list[FactRow]:
    """Resolve contradictions using court_ruling > police_affidavit > news_report."""
    rows: list[FactRow] = []
    for index, group in enumerate(groups):
        topic = str(group.get("topic") or f"topic-{index}")
        claims = group.get("claims")
        if not isinstance(claims, Sequence):
            continue
        parsed: list[tuple[str, str, str]] = []
        for item in claims:
            if not isinstance(item, Mapping):
                continue
            source = str(item.get("source_type") or "news_report")
            summary = str(item.get("event_summary") or "")
            parsed.append((source, summary, topic))
        if not parsed:
            continue
        winner = max(parsed, key=lambda row: SOURCE_RANK.get(row[0], 0))
        disputed = len({row[0] for row in parsed}) > 1 and len({row[1] for row in parsed}) > 1
        hedging = 1 if winner[0] == "news_report" else 0
        rows.append(
            FactRow(
                fact_id=f"fact-{index}",
                event_summary=winner[1],
                source_type=winner[0],
                hedging_required=hedging,
                disputed=disputed,
                winning_source=winner[0],
            )
        )
    return rows


def apply_hedging_tags(facts: Sequence[FactRow]) -> tuple[FactRow, ...]:
    tagged: list[FactRow] = []
    for fact in facts:
        hedging = 1 if fact.source_type == "news_report" else 0
        summary = fact.event_summary
        if hedging and not summary.lower().startswith("according to reports"):
            summary = f"According to reports, {summary[0].lower()}{summary[1:]}" if summary else summary
        tagged.append(
            FactRow(
                fact_id=fact.fact_id,
                event_summary=summary,
                source_type=fact.source_type,
                hedging_required=hedging,
                disputed=fact.disputed,
                winning_source=fact.winning_source,
            )
        )
    return tuple(tagged)


def extract_turning_points(candidates: Sequence[Mapping[str, Any]]) -> tuple[TurningPointBeat, ...] | str:
    beats: list[TurningPointBeat] = []
    for index, item in enumerate(candidates):
        if not isinstance(item, Mapping):
            continue
        summary = str(item.get("summary") or item.get("insight") or "").strip()
        if not summary:
            continue
        beats.append(
            TurningPointBeat(
                beat_id=str(item.get("beat_id") or f"beat-{index}"),
                summary=summary,
                source_type=str(item.get("source_type") or "court_ruling"),
            )
        )
    if len(beats) < MIN_TURNING_POINTS:
        return REJECTED_LOW_TWIST_DENSITY
    return tuple(beats)


def lock_early_2k_anchor(
    *,
    plate_png: bytes,
    grounding: Mapping[str, Any],
    fact_id: str,
) -> SpatialAnchor:
    span_cols = float(grounding.get("span_cols") or 1.0)
    span_rows = float(grounding.get("span_rows") or 1.0)
    raw_zoom = float(grounding.get("target_zoom") or 2.4)
    if span_cols > 1.0 or span_rows > 1.0:
        raw_zoom = min(raw_zoom, 1.8)
    target_zoom = max(1.6, min(3.8, raw_zoom))
    digest = hashlib.sha256(plate_png).hexdigest()
    return SpatialAnchor(
        anchor_id=f"anchor-{fact_id}",
        grid_cell=str(grounding.get("grid_cell") or "C5"),
        span_cols=span_cols,
        span_rows=span_rows,
        target_zoom=target_zoom,
        lock_status="LOCKED",
        still_asset_sha256=digest,
        is_illustrative_reconstruction=1,
    )


class Agent2EvidenceService:
    """Recorded-corpus evidence suite. Reads local fixtures and runs stage rules."""

    def __init__(self, fixtures: Path | str) -> None:
        self.fixtures = Path(fixtures)

    def _read(self, name: str) -> dict[str, object]:
        return load_json(self.fixtures / name)

    def run_disposition(self, name: str = "disposition_gate.json") -> GateDecision:
        fixture = self._read(name)
        return verify_disposition(
            fixture["suspect_names"],  # type: ignore[arg-type]
            int(fixture["incident_year"]),  # type: ignore[arg-type]
            fixture["docket_ids"],  # type: ignore[arg-type]
            courtlistener=lambda *_: fixture.get("courtlistener"),
            doc=lambda *_: fixture.get("state_doc"),
            gov=lambda *_: fixture.get("gov"),
        )

    def run_news(self, name: str = "news_text_only.json") -> NewsTextResult:
        fixture = self._read(name)
        return extract_news_text_only(str(fixture["html"]))

    def run_harvest(self, name: str = "courtlistener_harvest.json") -> HarvestState:
        fixture = self._read(name)
        return plan_courtlistener_harvest(
            calls_used=int(fixture["calls_used"]),  # type: ignore[arg-type]
            pending_calls=int(fixture["pending_calls"]),  # type: ignore[arg-type]
            cached_doc_ids=fixture.get("cached_doc_ids") or [],  # type: ignore[arg-type]
            queue_doc_ids=fixture.get("queue_doc_ids") or [],  # type: ignore[arg-type]
        )

    def run_anonymize(self, name: str = "anonymize.json") -> tuple[str, dict[str, str]]:
        fixture = self._read(name)
        return alias_unconvicted_third_parties(
            str(fixture["text"]),
            defendant_name=str(fixture["defendant_name"]),
            unconvicted_names=fixture["unconvicted_names"],  # type: ignore[arg-type]
        )

    def run_reconcile(self, name: str = "conflict_groups.json") -> tuple[FactRow, ...]:
        fixture = self._read(name)
        groups = fixture.get("groups") or []
        if not isinstance(groups, Sequence):
            raise TypeError("groups must be a list")
        rows = reconcile_conflicts([g for g in groups if isinstance(g, Mapping)])
        return apply_hedging_tags(rows)

    def run_turning_points(self, name: str = "turning_points.json") -> tuple[TurningPointBeat, ...] | str:
        fixture = self._read(name)
        candidates = fixture.get("candidates") or []
        if not isinstance(candidates, Sequence):
            raise TypeError("candidates must be a list")
        return extract_turning_points([c for c in candidates if isinstance(c, Mapping)])

    def run_2k_lock(self, name: str = "early_2k_lock.json") -> SpatialAnchor:
        fixture = self._read(name)
        plate_path = Path(str(fixture["plate_path"]))
        if not plate_path.is_absolute():
            plate_path = self.fixtures / plate_path
        plate = plate_path.read_bytes()
        grounding = fixture.get("grounding") or {}
        if not isinstance(grounding, Mapping):
            raise TypeError("grounding must be an object")
        return lock_early_2k_anchor(
            plate_png=plate,
            grounding=grounding,
            fact_id=str(fixture.get("fact_id") or "fact-0"),
        )

    def run_case(self, name: str = "affirmed_e2e.json") -> PipelineOutcome:
        """Full offline replay through disposition, harvest, ledger, 2K lock."""
        fixture = self._read(name)
        case_id = str(fixture.get("case_id") or "case")
        stages: list[str] = []

        gate = verify_disposition(
            fixture["suspect_names"],  # type: ignore[arg-type]
            int(fixture["incident_year"]),  # type: ignore[arg-type]
            fixture["docket_ids"],  # type: ignore[arg-type]
            courtlistener=lambda *_: fixture.get("courtlistener"),
            doc=lambda *_: fixture.get("state_doc"),
            gov=lambda *_: fixture.get("gov"),
        )
        stages.append("disposition_gate")
        if not gate.passed:
            return PipelineOutcome(
                case_id=case_id,
                conveyor_state=str(fixture.get("kill_state") or "KILLED_DISPOSITION"),
                gate=gate,
                anonymization_status="NOT_STARTED",
                anonymized_names={},
                news=None,
                facts=(),
                turning_points=(),
                anchors=(),
                harvest=None,
                stages=tuple(stages),
                failure_reason=gate.reason,
            )

        harvest_fixture = fixture.get("harvest") or {}
        harvest: HarvestState | None = None
        if isinstance(harvest_fixture, Mapping):
            harvest = plan_courtlistener_harvest(
                calls_used=int(harvest_fixture.get("calls_used") or 0),
                pending_calls=int(harvest_fixture.get("pending_calls") or 0),
                cached_doc_ids=harvest_fixture.get("cached_doc_ids") or [],  # type: ignore[arg-type]
                queue_doc_ids=harvest_fixture.get("queue_doc_ids") or [],  # type: ignore[arg-type]
            )
            stages.append("courtlistener_harvest")
            if harvest.parked:
                return PipelineOutcome(
                    case_id=case_id,
                    conveyor_state=PARKED_COURTLISTENER_QUOTA,
                    gate=gate,
                    anonymization_status="NOT_STARTED",
                    anonymized_names={},
                    news=None,
                    facts=(),
                    turning_points=(),
                    anchors=(),
                    harvest=harvest,
                    stages=tuple(stages),
                    failure_reason=PARKED_COURTLISTENER_QUOTA,
                )

        news_result: NewsTextResult | None = None
        if "news_html" in fixture:
            news_result = extract_news_text_only(str(fixture["news_html"]))
            stages.append("news_text_only")

        anon_status = "NOT_STARTED"
        anonymized: dict[str, str] = {}
        ledger_text = str(fixture.get("ledger_text") or "")
        if ledger_text:
            anonymized_text, anonymized = alias_unconvicted_third_parties(
                ledger_text,
                defendant_name=str(fixture.get("defendant_name") or ""),
                unconvicted_names=fixture.get("unconvicted_names") or [],  # type: ignore[arg-type]
            )
            ledger_text = anonymized_text
            anon_status = "IN_REVIEW"
            stages.append("anonymize")

        facts: tuple[FactRow, ...] = ()
        groups = fixture.get("conflict_groups")
        if isinstance(groups, Sequence):
            rows = reconcile_conflicts([g for g in groups if isinstance(g, Mapping)])
            facts = apply_hedging_tags(rows)
            stages.extend(("conflict_reconcile", "hedging"))

        turning: tuple[TurningPointBeat, ...] | str = ()
        candidates = fixture.get("turning_point_candidates")
        if isinstance(candidates, Sequence):
            turning = extract_turning_points([c for c in candidates if isinstance(c, Mapping)])
            stages.append("turning_points")
            if turning == REJECTED_LOW_TWIST_DENSITY:
                return PipelineOutcome(
                    case_id=case_id,
                    conveyor_state=REJECTED_LOW_TWIST_DENSITY,
                    gate=gate,
                    anonymization_status=anon_status,
                    anonymized_names=anonymized,
                    news=news_result,
                    facts=facts,
                    turning_points=(),
                    anchors=(),
                    harvest=harvest,
                    stages=tuple(stages),
                    failure_reason=REJECTED_LOW_TWIST_DENSITY,
                )

        anchors: tuple[SpatialAnchor, ...] = ()
        lock_spec = fixture.get("early_2k")
        if isinstance(lock_spec, Mapping):
            plate_path = Path(str(lock_spec.get("plate_path") or "plate_mock.png"))
            if not plate_path.is_absolute():
                plate_path = self.fixtures / plate_path
            plate = plate_path.read_bytes()
            grounding = lock_spec.get("grounding") or {}
            if not isinstance(grounding, Mapping):
                grounding = {}
            anchor = lock_early_2k_anchor(
                plate_png=plate,
                grounding=grounding,
                fact_id=str(lock_spec.get("fact_id") or "fact-0"),
            )
            anchors = (anchor,)
            stages.append("early_2k_lock")

        return PipelineOutcome(
            case_id=case_id,
            conveyor_state=EVIDENCE_AND_2K_LOCKED,
            gate=gate,
            anonymization_status=anon_status,
            anonymized_names=anonymized,
            news=news_result,
            facts=facts,
            turning_points=turning if isinstance(turning, tuple) else (),
            anchors=anchors,
            harvest=harvest,
            stages=tuple(stages),
        )


__all__ = [
    "Agent2EvidenceService",
    "COURTLISTENER_CALL_LIMIT",
    "EVIDENCE_AND_2K_LOCKED",
    "GateDecision",
    "PipelineOutcome",
    "REJECTED_LOW_TWIST_DENSITY",
]