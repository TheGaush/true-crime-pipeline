"""Chronology and citation verifier tests (DST, travel, citations)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
for _extra in (
    ROOT / "packages" / "agent2_evidence" / "src",
    ROOT / "packages" / "shared_contracts" / "src",
):
    _entry = str(_extra)
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from agent2_evidence.chronology_verifier import (  # noqa: E402
    parse_utc_instant,
    verify_chronology,
)
from shared_contracts.models import TemporalFact, TemporalFactLedger  # noqa: E402

_CASE = "case_dst_1"
_DOC = "doc_aff_1"
_BODY = (
    "AFFIDAVIT OF DEPUTY CLARK\n"
    "Page 1 describes the porch entry.\n"
    "Affidavit p. 2 notes the suspect departed eastbound.\n"
)


def _fact(
    fact_id: str,
    *,
    datetime_iso: str,
    location_text: str = "County courthouse",
    citation_locator: str = "Affidavit p. 2",
    event_summary: str = "Event noted in primary record",
) -> dict:
    return {
        "fact_id": fact_id,
        "case_id": _CASE,
        "datetime_iso": datetime_iso,
        "event_summary": event_summary,
        "physical_clues_json": [],
        "location_text": location_text,
        "source_type": "police_affidavit",
        "source_doc_id": _DOC,
        "citation_locator": citation_locator,
        "hedging_required": False,
        "contradicts_json": [],
    }


def _ledger(*facts: dict) -> TemporalFactLedger:
    return TemporalFactLedger.model_validate(
        {"contract_version": "v4", "case_id": _CASE, "facts": list(facts)}
    )


def test_dst_fallback_offsets_are_distinct_instants() -> None:
    edt = parse_utc_instant("2019-11-03T01:30:00-04:00")
    est = parse_utc_instant("2019-11-03T01:30:00-05:00")
    assert edt != est
    assert (est - edt).total_seconds() == 3600

    ledger = _ledger(
        _fact("fact_edt", datetime_iso="2019-11-03T01:30:00-04:00"),
        _fact("fact_est", datetime_iso="2019-11-03T01:30:00-05:00"),
    )
    verdict = verify_chronology(
        ledger, {_DOC: _BODY}, travel_minutes_lookup=lambda _a, _b: 0
    )
    assert verdict.passed
    assert "DUPLICATE_TIMESTAMP" not in verdict.issue_codes


def test_missing_utc_offset_fails() -> None:
    with pytest.raises(ValueError, match="explicit UTC offset"):
        parse_utc_instant("2019-06-01T12:00:00")

    bad = TemporalFact.model_construct(**_fact("fact_bad", datetime_iso="2019-06-01T12:00:00"))
    ledger = TemporalFactLedger.model_construct(
        contract_version="v4", case_id=_CASE, facts=[bad]
    )
    verdict = verify_chronology(ledger, {_DOC: _BODY}, default_travel_minutes=0)
    assert not verdict.passed
    assert verdict.issue_codes == frozenset({"MISSING_UTC_OFFSET"})


def test_impossible_travel_interval_flagged() -> None:
    ledger = _ledger(
        _fact(
            "fact_nyc",
            datetime_iso="2019-06-01T14:00:00-04:00",
            location_text="New York, NY",
        ),
        _fact(
            "fact_la",
            datetime_iso="2019-06-01T14:05:00-07:00",
            location_text="Los Angeles, CA",
        ),
    )

    def _drive_minutes(origin: str, dest: str) -> int | None:
        pair = {origin.casefold(), dest.casefold()}
        if pair == {"new york, ny", "los angeles, ca"}:
            return 300
        return None

    verdict = verify_chronology(
        ledger, {_DOC: _BODY}, travel_minutes_lookup=_drive_minutes
    )
    assert not verdict.passed
    assert "IMPOSSIBLE_TRAVEL" in verdict.issue_codes
    travel = [issue for issue in verdict.issues if issue.code == "IMPOSSIBLE_TRAVEL"]
    assert travel[0].fact_id == "fact_la"


def test_citation_locator_must_appear_in_document() -> None:
    ledger = _ledger(_fact("fact_ok", datetime_iso="2019-06-01T14:00:00-04:00"))
    verdict = verify_chronology(
        ledger, {_DOC: _BODY}, default_travel_minutes=0
    )
    assert verdict.passed


def test_missing_citation_locator_fails() -> None:
    ledger = _ledger(
        _fact(
            "fact_blank_loc",
            datetime_iso="2019-06-01T14:00:00-04:00",
            citation_locator="   ",
        )
    )
    verdict = verify_chronology(ledger, {_DOC: _BODY}, default_travel_minutes=0)
    assert not verdict.passed
    assert "MISSING_CITATION_LOCATOR" in verdict.issue_codes


def test_unresolved_citation_locator_fails() -> None:
    ledger = _ledger(
        _fact(
            "fact_missing_quote",
            datetime_iso="2019-06-01T14:00:00-04:00",
            citation_locator="paragraph 999",
        )
    )
    verdict = verify_chronology(ledger, {_DOC: _BODY}, default_travel_minutes=0)
    assert not verdict.passed
    assert "CITATION_UNRESOLVED" in verdict.issue_codes


def test_duplicate_exact_datetime_iso_string_fails() -> None:
    ledger = _ledger(
        _fact("fact_a", datetime_iso="2019-06-01T14:00:00-04:00"),
        _fact("fact_b", datetime_iso="2019-06-01T14:00:00-04:00"),
    )
    verdict = verify_chronology(ledger, {_DOC: _BODY}, default_travel_minutes=0)
    assert not verdict.passed
    assert "DUPLICATE_TIMESTAMP" in verdict.issue_codes


def test_normalize_whitespace_for_citation_match() -> None:
    ledger = _ledger(
        _fact(
            "fact_ws",
            datetime_iso="2019-06-01T14:00:00-04:00",
            citation_locator="Affidavit  p.  2",
        )
    )
    verdict = verify_chronology(ledger, {_DOC: _BODY}, default_travel_minutes=0)
    assert verdict.passed