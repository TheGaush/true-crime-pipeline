"""Offline Agent 2 end-to-end integration suite. Fixtures only. No network."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent2_evidence.pipeline import (
    COURTLISTENER_CALL_LIMIT,
    EVIDENCE_AND_2K_LOCKED,
    PARKED_COURTLISTENER_QUOTA,
    REJECTED_LOW_TWIST_DENSITY,
    Agent2EvidenceService,
    ILLUSTRATIVE_DISCLAIMER,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SERVICE = Agent2EvidenceService(FIXTURES)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_disposition_affirmed_passes() -> None:
    decision = SERVICE.run_disposition("disposition_affirmed.json")

    assert decision.passed
    assert decision.disposition_status == "AFFIRMED"
    assert decision.reason == "PASS_AFFIRMED"


def test_disposition_reversed_is_killed() -> None:
    decision = SERVICE.run_disposition("disposition_reversed.json")

    assert not decision.passed
    assert decision.disposition_status == "REVERSED"
    assert decision.reason == "APPELLATE_REVERSED"


def test_news_text_only_drops_media_bytes() -> None:
    result = SERVICE.run_news()

    assert result.doc_type == "news_text_only"
    assert result.retained_media_bytes == 0
    assert "Prosecutors filed the affidavit" in result.text
    assert "Neighbors described" in result.text
    assert "<img" not in result.text.lower()
    assert "base64," not in result.text.lower()


def test_courtlistener_harvest_parks_before_exceeding_62_calls() -> None:
    fixture = _load("courtlistener_harvest.json")
    harvest = SERVICE.run_harvest()

    assert harvest.parked
    assert harvest.calls_used == fixture["calls_used"]
    assert harvest.requested_calls == fixture["pending_calls"]
    assert harvest.calls_used + harvest.requested_calls > COURTLISTENER_CALL_LIMIT
    assert harvest.cached_doc_ids == tuple(fixture["cached_doc_ids"])


def test_unconvicted_third_parties_are_aliased() -> None:
    fixture = _load("anonymize.json")
    text, aliases = SERVICE.run_anonymize()

    assert aliases["Jane Doe"] == "Witness A"
    assert aliases["Sam Ortiz"] == "Neighbor A"
    assert fixture["defendant_name"] in text
    assert "Jane Doe" not in text
    assert "Sam Ortiz" not in text
    assert "Witness A" in text


def test_conflicts_follow_court_over_affidavit_over_news() -> None:
    facts = SERVICE.run_reconcile()
    location = next(f for f in facts if "warehouse" in f.event_summary)

    assert location.winning_source == "court_ruling"
    assert location.source_type == "court_ruling"
    assert location.hedging_required == 0

    news_only = next(f for f in facts if "blogger" in f.event_summary.lower())
    assert news_only.hedging_required == 1
    assert news_only.event_summary.startswith("According to reports,")


def test_fewer_than_three_turning_points_rejects_case() -> None:
    outcome = extract_turning_points_rejection = SERVICE.run_turning_points(
        "turning_points_thin.json"
    )

    assert extract_turning_points_rejection == REJECTED_LOW_TWIST_DENSITY

    thin = SERVICE.run_case("affirmed_e2e.json")
    thin_fixture = dict(_load("affirmed_e2e.json"))
    thin_fixture["turning_point_candidates"] = _load("turning_points_thin.json")["candidates"]
    path = FIXTURES / "_thin_runtime.json"
    path.write_text(json.dumps(thin_fixture), encoding="utf-8")
    try:
        rejected = Agent2EvidenceService(FIXTURES).run_case("_thin_runtime.json")
        assert rejected.conveyor_state == REJECTED_LOW_TWIST_DENSITY
        assert rejected.failure_reason == REJECTED_LOW_TWIST_DENSITY
        assert "early_2k_lock" not in rejected.stages
    finally:
        path.unlink(missing_ok=True)
    del thin


def test_mocked_2k_plate_locks_illustrative_anchor() -> None:
    fixture = _load("early_2k_lock.json")
    plate = (FIXTURES / fixture["plate_path"]).read_bytes()
    anchor = SERVICE.run_2k_lock()

    assert anchor.lock_status == "LOCKED"
    assert anchor.is_illustrative_reconstruction == 1
    assert anchor.still_asset_sha256 == hashlib.sha256(plate).hexdigest()
    assert anchor.grid_cell == fixture["grounding"]["grid_cell"]
    assert anchor.target_zoom <= 1.8
    assert ILLUSTRATIVE_DISCLAIMER


def test_full_affirmed_replay_reaches_evidence_and_2k_locked() -> None:
    outcome = SERVICE.run_case("affirmed_e2e.json")

    assert outcome.conveyor_state == EVIDENCE_AND_2K_LOCKED
    assert outcome.gate is not None and outcome.gate.passed
    assert outcome.anonymization_status == "IN_REVIEW"
    assert outcome.news is not None and outcome.news.retained_media_bytes == 0
    assert len(outcome.turning_points) >= 3
    assert len(outcome.anchors) == 1
    assert outcome.anchors[0].lock_status == "LOCKED"
    assert "disposition_gate" in outcome.stages
    assert "early_2k_lock" in outcome.stages


def test_reversed_full_replay_stops_at_disposition() -> None:
    outcome = SERVICE.run_case("reversed_e2e.json")

    assert outcome.conveyor_state == "KILLED_DISPOSITION"
    assert outcome.gate is not None and not outcome.gate.passed
    assert outcome.turning_points == ()
    assert outcome.anchors == ()
    assert outcome.stages == ("disposition_gate",)