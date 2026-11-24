"""Mandatory news_report hedging verifier tests."""

from __future__ import annotations

import ast
from pathlib import Path

from agent3_gatekeeper.hedging_verifier import (
    NEWS_ATTRIBUTION_PREFIX,
    RULE_09_CODE,
    UNKNOWN_FACT_CODE,
    ScriptBeat,
    beat_from_mapping,
    has_attribution_hedge,
    prefix_attribution,
    verify_beat_hedging,
    verify_beats_hedging,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "hedging_verifier.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}

_COURT_FACT = {
    "fact_id": "fact_court",
    "case_id": "case_demo",
    "datetime_iso": "2021-06-01T12:00:00Z",
    "event_summary": "The court held that the warrant was valid.",
    "physical_clues_json": [],
    "location_text": "Marlow County, Montana",
    "source_type": "court_ruling",
    "source_doc_id": "doc_ruling",
    "citation_locator": "2021 MT 142 ¶2",
    "hedging_required": 0,
    "contradicts_json": [],
}

_NEWS_FACT = {
    "fact_id": "fact_news",
    "case_id": "case_demo",
    "datetime_iso": "2019-04-04T09:00:00-06:00",
    "event_summary": "Neighbors noticed the porch light.",
    "physical_clues_json": [],
    "location_text": "Marlow County, Montana",
    "source_type": "news_report",
    "source_doc_id": "doc_news",
    "citation_locator": "Fixture Daily, 4 Apr 2019",
    "hedging_required": 1,
    "contradicts_json": [],
}

_AFFIDAVIT_FACT = {
    "fact_id": "fact_affidavit",
    "case_id": "case_demo",
    "datetime_iso": "2019-04-03T18:00:00Z",
    "event_summary": "The deputy logged shell casings.",
    "physical_clues_json": [],
    "location_text": "Marlow County, Montana",
    "source_type": "police_affidavit",
    "source_doc_id": "doc_affidavit",
    "citation_locator": "Affidavit p.3",
    "hedging_required": 0,
    "contradicts_json": [],
}

_LEDGER = [_COURT_FACT, _NEWS_FACT, _AFFIDAVIT_FACT]


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_court_only_beat_passes_without_hedge() -> None:
    beat = ScriptBeat(
        beat_id="b1",
        narration_text="The appellate court affirmed the homicide conviction.",
        cited_fact_ids=("fact_court",),
    )
    assert verify_beat_hedging(beat, _LEDGER) is None


def test_affidavit_only_beat_passes_without_hedge() -> None:
    beat = ScriptBeat(
        beat_id="b2",
        narration_text="According to the affidavit, shell casings were logged.",
        cited_fact_ids=("fact_affidavit",),
    )
    assert verify_beat_hedging(beat, _LEDGER) is None


def test_news_only_with_hedge_passes() -> None:
    beat = ScriptBeat(
        beat_id="b3",
        narration_text="News accounts reported that a porch light was on.",
        cited_fact_ids=("fact_news",),
    )
    assert verify_beat_hedging(beat, _LEDGER) is None


def test_news_only_without_hedge_fails_with_suggestion() -> None:
    beat = ScriptBeat(
        beat_id="b4",
        narration_text="A porch light was on that morning.",
        cited_fact_ids=("fact_news",),
    )
    failure = verify_beat_hedging(beat, _LEDGER)
    assert failure is not None
    assert failure.code == RULE_09_CODE
    assert failure.suggested_line == (
        "News accounts reported that a porch light was on that morning."
    )


def test_mixed_separated_clauses_pass_when_news_clause_hedged() -> None:
    beat = ScriptBeat(
        beat_id="b5",
        narration_text=(
            "The appellate court affirmed the homicide conviction; however, "
            "news accounts reported that neighbors saw a porch light on."
        ),
        cited_fact_ids=("fact_court", "fact_news"),
    )
    assert verify_beat_hedging(beat, _LEDGER) is None


def test_mixed_separated_clauses_fail_when_news_clause_unhedged() -> None:
    beat = ScriptBeat(
        beat_id="b6",
        narration_text=(
            "The appellate court affirmed the homicide conviction; however, "
            "local outlets said a porch light was on."
        ),
        cited_fact_ids=("fact_court", "fact_news"),
    )
    failure = verify_beat_hedging(beat, _LEDGER)
    assert failure is not None
    assert failure.code == RULE_09_CODE
    assert failure.suggested_line == (
        "The appellate court affirmed the homicide conviction; however, "
        "News accounts reported that local outlets said a porch light was on."
    )


def test_mixed_court_clause_without_hedge_is_allowed() -> None:
    """Court holding in the first clause must not require news attribution."""
    beat = ScriptBeat(
        beat_id="b7",
        narration_text=(
            "The court held the warrant was valid, but news accounts reported "
            "that neighbors noticed the porch light."
        ),
        cited_fact_ids=("fact_court", "fact_news"),
    )
    assert verify_beat_hedging(beat, _LEDGER) is None


def test_unknown_fact_id_fails() -> None:
    beat = ScriptBeat(
        beat_id="b8",
        narration_text="News accounts reported that something happened.",
        cited_fact_ids=("missing_fact",),
    )
    failure = verify_beat_hedging(beat, _LEDGER)
    assert failure is not None
    assert failure.code == UNKNOWN_FACT_CODE
    assert failure.suggested_line is None


def test_verify_beats_hedging_aggregates_failures() -> None:
    beats = [
        {
            "beat_id": "ok_court",
            "narration_text": "The court affirmed the conviction.",
            "cited_fact_ids": ["fact_court"],
        },
        {
            "beat_id": "bad_news",
            "approved_narration_text": "Neighbors saw a porch light.",
            "cited_fact_ids_json": ["fact_news"],
        },
    ]
    verdict = verify_beats_hedging(beats, _LEDGER)
    assert verdict.passed is False
    assert len(verdict.failures) == 1
    assert verdict.failures[0].beat_id == "bad_news"


def test_beat_from_mapping_reads_scene_plan_fields() -> None:
    beat = beat_from_mapping(
        {
            "scene_plan_id": "plan_42",
            "approved_narration_text": "Court held the warrant valid.",
            "cited_fact_ids_json": ["fact_court"],
        }
    )
    assert beat.beat_id == "plan_42"
    assert "warrant" in beat.narration_text


def test_has_attribution_hedge_and_prefix_idempotent() -> None:
    assert has_attribution_hedge("News accounts reported that it rained.")
    assert has_attribution_hedge("NEWS ACCOUNT REPORTED heavy smoke.")
    assert not has_attribution_hedge("Neighbors reported hearing shots.")

    once = prefix_attribution("A porch light was on.")
    twice = prefix_attribution(once)
    assert once == twice
    assert once.startswith(NEWS_ATTRIBUTION_PREFIX)