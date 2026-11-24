"""Offline primary-record disposition gate.

Lookups are injected. Nothing in this file opens a socket. The CourtListener
search fixture is read from disk and labeled in memory as AFFIRMED or REVERSED.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent2_evidence.primary_gate import (
    KILL_DISPOSITIONS,
    PASSING_DISPOSITIONS,
    GateDecision,
    PrimaryRecordVerifier,
)

FIXTURE = (
    Path(__file__).resolve().parents[3]
    / "fixtures"
    / "recorded_apis"
    / "courtlistener_search.json"
)

NAME = "Jane Roe"
YEAR = 2014
DOCKET = "2014-CR-100"


def _verifier(
    court: list[dict] | dict | None,
    doc: list[dict] | dict | None,
    gov: list[dict] | dict | None,
) -> PrimaryRecordVerifier:
    return PrimaryRecordVerifier(
        courtlistener=lambda _names, _year, _dockets: court,
        doc=lambda _names, _year, _dockets: doc,
        gov=lambda _names, _year, _dockets: gov,
    )


def _court(status: str | None = "AFFIRMED", **extra: object) -> dict:
    record: dict = {
        "suspect_names": [NAME],
        "incident_year": YEAR,
        "docket_id": DOCKET,
        "source": "courtlistener",
    }
    if status is not None:
        record["disposition"] = status
    record.update(extra)
    return record


def _doc(**extra: object) -> dict:
    record: dict = {
        "suspect_names": [NAME],
        "incident_year": YEAR,
        "docket_id": DOCKET,
        "conviction_standing": True,
    }
    record.update(extra)
    return record


def _gov(**extra: object) -> dict:
    record: dict = {
        "suspect_names": [NAME],
        "incident_year": YEAR,
        "docket_id": DOCKET,
        "source_domain": "doc.example.gov",
        "source_url": "https://doc.example.gov/releases/2014-cr-100",
    }
    record.update(extra)
    return record


def _check(court, doc, gov) -> GateDecision:
    return _verifier(court, doc, gov).verify([NAME], YEAR, [DOCKET])


def test_affirmed_case_passes() -> None:
    decision = _check([_court("AFFIRMED")], [_doc(disposition="AFFIRMED")], [_gov()])
    assert decision.passed
    assert decision.verdict == "PASS"
    assert decision.disposition_status == "AFFIRMED"
    assert decision.conviction_confirmed is True
    assert decision.primary_record_verified is True
    assert decision.reason == "PASS_AFFIRMED"
    assert decision.verification_source == "courtlistener+state_doc+gov"


def test_standing_conviction_passes() -> None:
    decision = _check(
        [_court("STANDING_CONVICTION")],
        [_doc(disposition="STANDING_CONVICTION")],
        [_gov(disposition="STANDING_CONVICTION")],
    )
    assert decision.passed
    assert decision.disposition_status == "STANDING_CONVICTION"
    assert decision.conviction_confirmed is True
    assert decision.reason == "PASS_STANDING_CONVICTION"


@pytest.mark.parametrize("status", ["REVERSED", "VACATED", "ACQUITTED", "PENDING"])
def test_killing_dispositions_are_hard_killed(status: str) -> None:
    decision = _check(
        [_court(status)],
        [_doc(disposition=status, conviction_standing=False)],
        [_gov(disposition=status)],
    )
    assert decision.killed
    assert decision.disposition_status == status
    assert decision.conviction_confirmed is False
    assert decision.primary_record_verified is True
    assert decision.reason == f"APPELLATE_{status}"
    assert decision.disposition_status not in PASSING_DISPOSITIONS


def test_court_reversal_kills_even_if_doc_still_lists_a_conviction() -> None:
    decision = _check(
        [_court("REVERSED")],
        [_doc(conviction_standing=True, disposition="AFFIRMED")],
        [_gov(disposition="AFFIRMED")],
    )
    assert decision.killed
    assert decision.reason == "APPELLATE_REVERSED"
    assert decision.disposition_status == "REVERSED"
    assert decision.conviction_confirmed is False


def test_nosleep_case_without_primary_record_is_killed() -> None:
    decision = _verifier([], [], []).verify(
        ["Narrator"],
        2016,
        ["r-nosleep-8841"],
    )
    assert decision.killed
    assert decision.reason == "FICTIONAL_NOSLEEP"
    assert decision.conviction_confirmed is False
    assert decision.primary_record_verified is False
    assert decision.disposition_status is None


def test_nosleep_record_claiming_affirmed_is_killed() -> None:
    fiction = {
        "suspect_names": ["Alex Story"],
        "incident_year": 2018,
        "docket_id": "FAKE-1",
        "disposition": "AFFIRMED",
        "origin": "nosleep",
        "source_domain": "www.reddit.com",
        "fictional": True,
    }
    decision = _verifier([fiction], [fiction], [fiction]).verify(
        ["Alex Story"],
        2018,
        ["FAKE-1"],
    )
    assert decision.killed
    assert decision.reason == "FICTIONAL_NOSLEEP"
    assert decision.conviction_confirmed is False
    assert decision.disposition_status is None


def test_unverified_lead_without_records_is_killed() -> None:
    decision = _verifier(None, None, None).verify(["Sam Witness"], 2001, ["2001-CR-9"])
    assert decision.killed
    assert decision.reason == "NO_PRIMARY_RECORD"
    assert decision.primary_record_verified is False
    assert decision.conviction_confirmed is False


def test_split_homicide_passes_only_when_doc_shows_the_conviction() -> None:
    court = _court(
        None,
        counts=[
            {"count": 1, "charge": "homicide", "disposition": "AFFIRMED"},
            {
                "count": 2,
                "charge": "procedural",
                "disposition": "REVERSED",
                "procedural": True,
            },
        ],
    )
    shown = _check(
        [court],
        [_doc(homicide_conviction_standing=True, standing_charges=["homicide"])],
        [_gov()],
    )
    assert shown.passed
    assert shown.disposition_status == "STANDING_CONVICTION"
    assert shown.conviction_confirmed is True
    assert shown.reason == "PASS_STANDING_CONVICTION"

    missing = _check(
        [court],
        [
            _doc(
                homicide_conviction_standing=False,
                conviction_standing=True,
                standing_charges=["procedural"],
            )
        ],
        [_gov()],
    )
    assert missing.killed
    assert missing.reason == "DOC_HOMICIDE_NOT_STANDING"
    assert missing.conviction_confirmed is False
    assert missing.disposition_status not in PASSING_DISPOSITIONS


def test_whole_conviction_vacated_kills_even_if_doc_shows_homicide() -> None:
    decision = _check(
        [
            _court(
                "VACATED",
                whole_conviction_vacated=True,
                counts=[
                    {"count": 1, "charge": "homicide", "disposition": "AFFIRMED"},
                    {"count": 2, "charge": "procedural", "disposition": "REVERSED"},
                ],
            )
        ],
        [_doc(homicide_conviction_standing=True, standing_charges=["homicide"])],
        [_gov()],
    )
    assert decision.killed
    assert decision.reason == "WHOLE_CONVICTION_VACATED"
    assert decision.disposition_status == "VACATED"
    assert decision.conviction_confirmed is False


def test_top_level_vacated_kills_even_with_an_affirmed_homicide_count() -> None:
    decision = _check(
        [
            _court(
                "VACATED",
                counts=[
                    {"count": 1, "charge": "homicide", "disposition": "AFFIRMED"},
                    {"count": 2, "charge": "procedural", "disposition": "REVERSED"},
                ],
            )
        ],
        [_doc(homicide_conviction_standing=True)],
        [_gov()],
    )
    assert decision.killed
    assert decision.disposition_status == "VACATED"
    assert decision.conviction_confirmed is False


def test_remand_for_new_trial_kills_even_if_a_count_says_affirmed() -> None:
    decision = _check(
        [
            _court(
                "AFFIRMED",
                remanded_for_new_trial=True,
                counts=[
                    {"count": 1, "charge": "homicide", "disposition": "AFFIRMED"},
                    {"count": 2, "charge": "procedural", "disposition": "REVERSED"},
                ],
            )
        ],
        [_doc(homicide_conviction_standing=True, standing_charges=["homicide"])],
        [_gov(disposition="AFFIRMED")],
    )
    assert decision.killed
    assert decision.reason == "REMANDED_FOR_NEW_TRIAL"
    assert decision.disposition_status == "PENDING"
    assert decision.conviction_confirmed is False
    assert decision.disposition_status not in PASSING_DISPOSITIONS


def test_reversed_homicide_count_is_killed() -> None:
    decision = _check(
        [
            _court(
                None,
                counts=[
                    {"count": 1, "charge": "homicide", "disposition": "REVERSED"},
                    {"count": 2, "charge": "procedural", "disposition": "AFFIRMED"},
                ],
            )
        ],
        [_doc(homicide_conviction_standing=True)],
        [_gov()],
    )
    assert decision.killed
    assert decision.reason == "APPELLATE_REVERSED"
    assert decision.disposition_status == "REVERSED"
    assert decision.conviction_confirmed is False


def test_identity_mismatch_is_not_a_primary_record() -> None:
    decision = _check(
        [_court("AFFIRMED", incident_year=YEAR + 1)],
        [_doc()],
        [_gov()],
    )
    assert decision.killed
    assert decision.reason == "INCOMPLETE_CORROBORATION"
    assert decision.conviction_confirmed is False


def test_non_gov_domain_does_not_corroborate() -> None:
    decision = _check(
        [_court("AFFIRMED")],
        [_doc(disposition="AFFIRMED")],
        [_gov(source_domain="example.com", source_url="https://example.com/release")],
    )
    assert decision.killed
    assert decision.reason == "INCOMPLETE_CORROBORATION"
    assert decision.passed is False


def test_missing_doc_channel_blocks_an_affirmed_opinion() -> None:
    decision = _check([_court("AFFIRMED")], [], [_gov()])
    assert decision.killed
    assert decision.reason == "INCOMPLETE_CORROBORATION"
    assert decision.conviction_confirmed is False


def test_doc_kill_overrides_an_affirmed_opinion() -> None:
    decision = _check(
        [_court("AFFIRMED")],
        [_doc(disposition="VACATED", conviction_standing=False)],
        [_gov(disposition="AFFIRMED")],
    )
    assert decision.killed
    assert decision.reason == "DISPOSITION_CONFLICT"
    assert decision.disposition_status == "VACATED"
    assert decision.conviction_confirmed is False


def test_gov_kill_overrides_an_affirmed_opinion() -> None:
    decision = _check(
        [_court("AFFIRMED")],
        [_doc(disposition="AFFIRMED")],
        [_gov(disposition="REVERSED")],
    )
    assert decision.killed
    assert decision.reason == "DISPOSITION_CONFLICT"
    assert decision.disposition_status == "REVERSED"
    assert decision.conviction_confirmed is False


def test_lookups_receive_the_query_keys() -> None:
    seen: dict[str, tuple] = {}

    def capture(channel: str):
        def _lookup(names, year, dockets):
            seen[channel] = (names, year, dockets)
            if channel == "courtlistener":
                return [_court("AFFIRMED")]
            if channel == "doc":
                return [_doc(disposition="AFFIRMED")]
            return [_gov()]

        return _lookup

    decision = PrimaryRecordVerifier(
        courtlistener=capture("courtlistener"),
        doc=capture("doc"),
        gov=capture("gov"),
    ).verify([" Jane Roe "], YEAR, [" 2014-CR-100 "])
    assert decision.passed
    expected = (("Jane Roe",), YEAR, ("2014-CR-100",))
    assert seen["courtlistener"] == expected
    assert seen["doc"] == expected
    assert seen["gov"] == expected


def test_recorded_fixture_affirmed_passes_and_reversed_kills() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    opinion = payload["results"][0]
    assert payload["fixture_controls"]["live_http"] is False
    assert opinion["docket_number"] == "2019-CR-1042"
    assert opinion["case_name"] == "State v. Hale"

    def decision_for(status: str) -> GateDecision:
        shared = {
            "suspect_names": ["Hale"],
            "incident_year": 2019,
            "docket_id": opinion["docket_number"],
            "case_name": opinion["case_name"],
            "disposition": status,
        }
        verifier = PrimaryRecordVerifier(
            courtlistener=lambda *_args: [{**shared, "source": "courtlistener"}],
            doc=lambda *_args: [
                {
                    **shared,
                    "conviction_standing": status in PASSING_DISPOSITIONS,
                }
            ],
            gov=lambda *_args: [{**shared, "source_domain": "courts.mt.gov"}],
        )
        return verifier.verify(["Hale"], 2019, [opinion["docket_number"]])

    affirmed = decision_for("AFFIRMED")
    assert affirmed.passed
    assert affirmed.disposition_status == "AFFIRMED"
    assert affirmed.conviction_confirmed is True

    reversed_decision = decision_for("REVERSED")
    assert reversed_decision.killed
    assert reversed_decision.disposition_status == "REVERSED"
    assert reversed_decision.conviction_confirmed is False
    assert reversed_decision.reason == "APPELLATE_REVERSED"


def test_kill_decisions_never_carry_a_passing_disposition() -> None:
    samples = [
        _check([_court(status)], [_doc(disposition=status, conviction_standing=False)], [_gov()])
        for status in KILL_DISPOSITIONS
    ]
    samples.append(_verifier([], [], []).verify(["Narrator"], 2016, ["nosleep-1"]))
    for decision in samples:
        assert decision.killed
        assert decision.conviction_confirmed is False
        assert decision.disposition_status not in PASSING_DISPOSITIONS


def test_invalid_query_is_killed() -> None:
    decision = _verifier([_court()], [_doc()], [_gov()]).verify([], YEAR, [DOCKET])
    assert decision.killed
    assert decision.reason == "INVALID_QUERY"
    assert decision.conviction_confirmed is False


def test_later_vacatur_beats_an_earlier_affirmance() -> None:
    decision = _check(
        [_court("AFFIRMED"), _court("VACATED")],
        [_doc(disposition="AFFIRMED")],
        [_gov(disposition="AFFIRMED")],
    )
    assert decision.killed
    assert decision.disposition_status == "VACATED"
    assert decision.conviction_confirmed is False
