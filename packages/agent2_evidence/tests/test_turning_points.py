"""Tests for the turning-point beat extractor."""

from __future__ import annotations

from agent2_evidence.turning_points import (
    MIN_TURNING_POINTS,
    REJECTED_LOW_TWIST_DENSITY,
    FactLedger,
    TwistFact,
    extract_turning_points,
)

_CASE_ID = "case_tp_demo"


def _three_twist_ledger() -> FactLedger:
    return FactLedger(
        case_id=_CASE_ID,
        facts=(
            TwistFact(
                fact_id="fact_alibi",
                datetime_iso="2015-03-12T18:30:00Z",
                event_summary=(
                    "Detectives noted the suspect's alibi was contradicted by toll records "
                    "showing the vehicle near the scene."
                ),
                source_type="police_affidavit",
                citation_locator="affidavit p.14",
                contradicts_fact_ids=("fact_alibi_claim",),
            ),
            TwistFact(
                fact_id="fact_alibi_claim",
                datetime_iso="2015-03-11T09:00:00Z",
                event_summary="The suspect said he stayed at his sister's house all night.",
                source_type="police_affidavit",
                citation_locator="affidavit p.6",
            ),
            TwistFact(
                fact_id="fact_dna",
                datetime_iso="2015-04-02T11:15:00Z",
                event_summary="The state crime lab reported a DNA match on the knife handle.",
                source_type="police_affidavit",
                citation_locator="lab report exhibit B",
                physical_clues=("knife handle swab", "CODIS hit"),
            ),
            TwistFact(
                fact_id="fact_appellate",
                datetime_iso="2017-09-21T16:00:00Z",
                event_summary=(
                    "The appellate panel affirmed the trial court judgment on the homicide count."
                ),
                source_type="court_ruling",
                citation_locator="opinion p.22",
            ),
        ),
    )


def _one_twist_ledger() -> FactLedger:
    return FactLedger(
        case_id=_CASE_ID,
        facts=(
            TwistFact(
                fact_id="fact_only",
                datetime_iso="2015-04-02T11:15:00Z",
                event_summary="Analysts documented a latent fingerprint match on the rear door.",
                source_type="police_affidavit",
                citation_locator="lab report exhibit C",
                physical_clues=("latent print",),
            ),
            TwistFact(
                fact_id="fact_noise",
                datetime_iso="2015-04-03T08:00:00Z",
                event_summary="Deputies logged the chain-of-custody transfer for sealed bags.",
                source_type="police_affidavit",
                citation_locator="property room log p.3",
            ),
        ),
    )


def test_three_twist_ledger_passes_with_required_kinds() -> None:
    result = extract_turning_points(_three_twist_ledger())

    assert result.accepted
    assert result.reason is None
    assert result.turning_point_count >= MIN_TURNING_POINTS
    assert len(result.beats) >= MIN_TURNING_POINTS
    assert result.anti_legal_persona_passed

    kinds = {beat.twist_kind for beat in result.beats}
    assert kinds >= {
        "discredited_alibi",
        "forensic_match",
        "appellate_holding",
    }

    for beat in result.beats:
        assert beat.editorial_analysis
        assert "legal advice" not in beat.editorial_analysis.casefold()
        assert beat.record_anchor.startswith("According to the")
        assert beat.citation_locator
        assert beat.fact_id


def test_one_twist_ledger_fails_low_density() -> None:
    result = extract_turning_points(_one_twist_ledger())

    assert result.rejected
    assert result.reason == REJECTED_LOW_TWIST_DENSITY
    assert result.beats == ()
    assert result.turning_point_count < MIN_TURNING_POINTS


def test_two_twist_ledger_still_rejects() -> None:
    ledger = FactLedger(
        case_id=_CASE_ID,
        facts=(
            TwistFact(
                fact_id="fact_a",
                datetime_iso="2015-03-12T18:30:00Z",
                event_summary="Investigators said the alibi was discredited by store receipts.",
                source_type="police_affidavit",
                citation_locator="affidavit p.9",
            ),
            TwistFact(
                fact_id="fact_b",
                datetime_iso="2015-04-02T11:15:00Z",
                event_summary="Ballistic testing tied a shell casing to the seized firearm.",
                source_type="police_affidavit",
                citation_locator="lab report exhibit D",
                physical_clues=("shell casing",),
            ),
            TwistFact(
                fact_id="fact_c",
                datetime_iso="2015-04-03T08:00:00Z",
                event_summary="Clerks filed the daily property-room inventory update.",
                source_type="police_affidavit",
                citation_locator="log p.1",
            ),
        ),
    )

    result = extract_turning_points(ledger)

    assert result.rejected
    assert result.reason == REJECTED_LOW_TWIST_DENSITY
    assert result.turning_point_count == 2