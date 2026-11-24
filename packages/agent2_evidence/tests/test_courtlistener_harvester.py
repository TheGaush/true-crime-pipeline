"""Offline tests for the CourtListener opinion harvester."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from agent2_evidence.courtlistener_harvester import CourtListenerHarvester, HarvestResult

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "state_v_hale_opinion.json"
FETCHED_AT = 1_700_000_000_000
CASE_ID = "case_test_hale"
OPINION_ID = "1042001"

PRIMARY_DOC_KEYS = {
    "doc_id",
    "case_id",
    "source_domain",
    "source_url",
    "doc_type",
    "raw_text_sha256",
    "local_text_path",
    "fetched_at",
}


class CountingFetcher:
    def __init__(self, opinion: dict) -> None:
        self.opinion = opinion
        self.call_ids: list[str] = []

    def __call__(self, opinion_id: str) -> dict:
        self.call_ids.append(opinion_id)
        if opinion_id != OPINION_ID:
            raise KeyError(opinion_id)
        return self.opinion


def load_fixture_opinion() -> dict:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert payload["live_http"] is False
    return payload["opinion"]


def harvest_once(harvester: CourtListenerHarvester) -> HarvestResult:
    return harvester.harvest(
        OPINION_ID,
        case_id=CASE_ID,
        fetched_at=FETCHED_AT,
    )


def test_splits_majority_concurring_dissent_and_tags_holdings() -> None:
    fetcher = CountingFetcher(load_fixture_opinion())
    harvester = CourtListenerHarvester(fetcher)
    result = harvest_once(harvester)
    roles = {section.role for section in result.harvested.sections}
    assert roles == {"majority", "concurring", "dissent"}
    for section in result.harvested.sections:
        if section.role == "majority":
            assert section.is_holding is True
        else:
            assert section.is_holding is False
    assert "speculates" in next(s.text for s in result.harvested.sections if s.role == "dissent")
    assert "forensic match" in result.harvested.majority_text
    assert "[DISSENT]" in result.harvested.full_normalized_text


def test_preserves_citation_locators() -> None:
    fetcher = CountingFetcher(load_fixture_opinion())
    result = harvest_once(CourtListenerHarvester(fetcher))
    locators = result.harvested.citation_locators
    assert "p. 12, para. 3" in locators
    assert "pp. 14-15, para. 2" in locators
    assert "p. 22, para. 4" in locators
    assert "p. 12, para. 3" in result.harvested.full_normalized_text


def test_in_memory_cache_skips_second_fetch() -> None:
    fetcher = CountingFetcher(load_fixture_opinion())
    harvester = CourtListenerHarvester(fetcher)
    first = harvest_once(harvester)
    second = harvest_once(harvester)
    assert len(fetcher.call_ids) == 1
    assert harvester.fetch_call_count == 1
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.harvested.full_normalized_text == second.harvested.full_normalized_text


def test_primary_document_shape_and_hash() -> None:
    fetcher = CountingFetcher(load_fixture_opinion())
    result = harvest_once(CourtListenerHarvester(fetcher))
    doc = result.primary_document
    assert set(doc) == PRIMARY_DOC_KEYS
    assert doc["doc_type"] == "court_ruling"
    assert doc["case_id"] == CASE_ID
    assert doc["source_domain"] == "www.courtlistener.com"
    assert doc["source_url"].endswith("/state-v-hale/")
    digest = hashlib.sha256(result.harvested.full_normalized_text.encode("utf-8")).hexdigest()
    assert doc["raw_text_sha256"] == digest
    assert doc["fetched_at"] == FETCHED_AT