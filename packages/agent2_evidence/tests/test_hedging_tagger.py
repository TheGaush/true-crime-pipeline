"""Tests for source-tier hedging tagger and RULE_09 SQLite triggers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent2_evidence.hedging_tagger import (
    NEWS_ATTRIBUTION_PREFIX,
    RULE_09_MESSAGE,
    TaggedFact,
    enforce_rule_09,
    hedging_flag_for,
    prefix_news_attribution,
    tag_facts_for_hedging,
    validate_hedging_before_insert,
    validate_hedging_before_update,
)

SCHEMA = Path(__file__).resolve().parents[3] / "schema" / "pipeline.sql"

_COMPOSITE = {
    "fact_id": "case_demo_fact_mixed",
    "case_id": "case_demo",
    "datetime_iso": "2019-04-04T09:00:00-06:00",
    "event_summary": (
        "The appellate court affirmed the homicide conviction; however, "
        "local news outlets reported that a neighbor saw a porch light on."
    ),
    "physical_clues_json": [],
    "location_text": "Marlow County, Montana",
    "source_type": "court_ruling",
    "source_doc_id": "case_demo_doc_ruling",
    "citation_locator": "2021 MT 142 ¶18",
    "hedging_required": 0,
    "contradicts_json": [],
    "news_source_doc_id": "case_demo_doc_news",
    "news_citation_locator": "Fixture Daily, 4 Apr 2019",
}

_COURT_ONLY = {
    "fact_id": "case_demo_fact_court",
    "case_id": "case_demo",
    "datetime_iso": "2021-06-01T12:00:00Z",
    "event_summary": "The court held that the search warrant was valid.",
    "physical_clues_json": [],
    "location_text": "Marlow County, Montana",
    "source_type": "court_ruling",
    "source_doc_id": "case_demo_doc_ruling",
    "citation_locator": "2021 MT 142 ¶2",
    "hedging_required": 0,
    "contradicts_json": [],
}

_NEWS_ONLY = {
    "fact_id": "case_demo_fact_news",
    "case_id": "case_demo",
    "datetime_iso": "2019-04-04T09:00:00-06:00",
    "event_summary": "neighbors noticed the porch light.",
    "physical_clues_json": [],
    "location_text": "Marlow County, Montana",
    "source_type": "news_report",
    "source_doc_id": "case_demo_doc_news",
    "citation_locator": "Fixture Daily, 4 Apr 2019",
    "hedging_required": 0,
    "contradicts_json": [],
}


def _load_pipeline_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _seed_case(conn: sqlite3.Connection) -> None:
    conn.execute(
        """INSERT INTO cases (
             case_id, defendant_name, incident_year, jurisdiction, docket_id,
             primary_record_verified, verification_source, disposition_status,
             conviction_confirmed, anonymization_status, anonymized_by, anonymized_at,
             anonymization_artifact_sha256, created_at, updated_at
           ) VALUES (
             'case_demo','Jane Roe',2019,'Marlow, MT','DK-DEMO',1,'courtlistener',
             'AFFIRMED',1,'APPROVED','reviewer',1000,'sha',1000,1000
           )"""
    )
    conn.execute(
        """INSERT INTO primary_documents
           VALUES ('case_demo_doc_ruling','case_demo','courts.mt.example',
                   'https://courts.mt.example/opinion','court_ruling','abc','/tmp/r.txt',1000)"""
    )
    conn.execute(
        """INSERT INTO primary_documents
           VALUES ('case_demo_doc_news','case_demo','daily.example',
                   'https://daily.example/story','news_text_only','def','/tmp/n.txt',1000)"""
    )


def test_split_composite_court_and_news() -> None:
    tagged = tag_facts_for_hedging([_COMPOSITE])
    assert len(tagged) == 2
    court, news = tagged
    assert isinstance(court, TaggedFact)
    assert court.source_type == "court_ruling"
    assert court.hedging_required == 0
    assert court.fact_id.endswith("__court")
    assert "appellate court" in court.event_summary.lower()
    assert not court.event_summary.startswith(NEWS_ATTRIBUTION_PREFIX)

    assert news.source_type == "news_report"
    assert news.hedging_required == 1
    assert news.fact_id.endswith("__news")
    assert news.source_doc_id == "case_demo_doc_news"
    assert news.event_summary.startswith(NEWS_ATTRIBUTION_PREFIX)
    assert "porch light" in news.event_summary.lower()


def test_news_only_gets_prefix_and_hedge() -> None:
    (news,) = tag_facts_for_hedging([_NEWS_ONLY])
    assert news.hedging_required == 1
    assert news.event_summary.startswith(NEWS_ATTRIBUTION_PREFIX)


def test_court_only_stays_unhedged() -> None:
    (court,) = tag_facts_for_hedging([_COURT_ONLY])
    assert court.hedging_required == 0
    assert court.event_summary == _COURT_ONLY["event_summary"]


def test_python_rule_09_rejects_unhedged_news() -> None:
    with pytest.raises(ValueError, match="RULE_09"):
        enforce_rule_09("news_report", 0)
    with pytest.raises(ValueError, match="RULE_09"):
        validate_hedging_before_insert(
            {"source_type": "news_report", "hedging_required": 0}
        )
    with pytest.raises(ValueError, match="RULE_09"):
        validate_hedging_before_update(
            {"source_type": "news_report", "hedging_required": 0}
        )


def test_prefix_news_attribution_idempotent() -> None:
    once = prefix_news_attribution("a porch light was on.")
    twice = prefix_news_attribution(once)
    assert once == twice
    assert once.startswith(NEWS_ATTRIBUTION_PREFIX)


def test_hedging_flag_for_source_tiers() -> None:
    assert hedging_flag_for("news_report") == 1
    assert hedging_flag_for("court_ruling") == 0
    assert hedging_flag_for("police_affidavit") == 0


def test_sqlite_insert_trigger_rejects_unhedged_news() -> None:
    conn = _load_pipeline_db()
    try:
        _seed_case(conn)
        (news,) = tag_facts_for_hedging([_NEWS_ONLY])
        conn.execute(
            """INSERT INTO fact_ledger (
                 fact_id, case_id, datetime_iso, event_summary, physical_clues_json,
                 location_text, source_type, source_doc_id, citation_locator,
                 hedging_required, contradicts_json
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                news.fact_id,
                news.case_id,
                news.datetime_iso,
                news.event_summary,
                "[]",
                news.location_text,
                news.source_type,
                news.source_doc_id,
                news.citation_locator,
                news.hedging_required,
                "[]",
            ),
        )
        with pytest.raises(sqlite3.Error, match="RULE_09"):
            conn.execute(
                """INSERT INTO fact_ledger VALUES (
                     'bad_news','case_demo','2019-04-04T09:00:00-06:00',
                     'Unhedged rumor','[]','Marlow County','news_report',
                     'case_demo_doc_news','p.1',0,'[]')"""
            )
    finally:
        conn.close()


def test_sqlite_update_trigger_rejects_hedge_downgrade() -> None:
    conn = _load_pipeline_db()
    try:
        _seed_case(conn)
        (news,) = tag_facts_for_hedging([_NEWS_ONLY])
        conn.execute(
            """INSERT INTO fact_ledger VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                news.fact_id,
                news.case_id,
                news.datetime_iso,
                news.event_summary,
                "[]",
                news.location_text,
                news.source_type,
                news.source_doc_id,
                news.citation_locator,
                news.hedging_required,
                "[]",
            ),
        )
        with pytest.raises(sqlite3.Error, match="RULE_09"):
            conn.execute(
                """UPDATE fact_ledger SET hedging_required = 0 WHERE fact_id = ?""",
                (news.fact_id,),
            )
    finally:
        conn.close()