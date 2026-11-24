"""Judicial hierarchy and alibi reconciliation tests. No network."""

from __future__ import annotations

import json
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

from agent2_evidence.conflict_reconciler import (  # noqa: E402
    PROMPT_CONTRACT_ID,
    TOOLS_ENABLED,
    WRITES_DATABASE,
    ConflictReconciler,
    ConflictReconciliationError,
    load_reasoning_model_id,
)
from shared_contracts.models import TemporalFact, TemporalFactLedger  # noqa: E402

PROVIDERS = ROOT / "providers.yaml"
MODEL_ID = "DeepSeek-V4-Pro-0813"


def _fact(
    fact_id: str,
    *,
    source_type: str,
    summary: str,
    contradicts: list[str] | None = None,
) -> TemporalFact:
    return TemporalFact.model_validate(
        {
            "fact_id": fact_id,
            "case_id": "case_hale",
            "datetime_iso": "2014-06-02T21:00:00Z",
            "event_summary": summary,
            "physical_clues_json": [],
            "location_text": "entryway",
            "source_type": source_type,
            "source_doc_id": f"doc_{fact_id}",
            "citation_locator": "p.1",
            "hedging_required": source_type == "news_report",
            "contradicts_json": contradicts or [],
        }
    )


def _ledger(*facts: TemporalFact) -> TemporalFactLedger:
    return TemporalFactLedger(contract_version="v4", case_id="case_hale", facts=list(facts))


def _client(response: dict[str, object]):
    calls: list[tuple[str, str]] = []

    def model_client(model_id: str, prompt: str) -> str:
        calls.append((model_id, prompt))
        return json.dumps(response)

    return model_client, calls


def test_reasoning_model_id_loads_from_providers_yaml() -> None:
    assert load_reasoning_model_id(PROVIDERS) == MODEL_ID


def test_cross_tier_court_ruling_beats_news_report() -> None:
    news = _fact("fact_news_alibi", source_type="news_report", summary="Defendant was home per neighbors.")
    court = _fact(
        "fact_court_toll",
        source_type="court_ruling",
        summary="The toll record places the defendant away from home.",
    )
    payload = {
        "conflict_groups": [
            {
                "fact_ids": ["fact_news_alibi", "fact_court_toll"],
                "alibi_fact_id": "fact_news_alibi",
                "discrediting_fact_id": "fact_court_toll",
            }
        ]
    }
    client, calls = _client(payload)
    result = ConflictReconciler(PROVIDERS, model_client=client).reconcile(_ledger(news, court))

    assert calls[0][0] == MODEL_ID
    assert result.prompt_contract_id == PROMPT_CONTRACT_ID
    assert result.model_id == MODEL_ID
    news_row = next(item for item in result.facts if item.fact.fact_id == "fact_news_alibi")
    court_row = next(item for item in result.facts if item.fact.fact_id == "fact_court_toll")
    assert news_row.disputed is False
    assert court_row.disputed is False
    assert "fact_court_toll" in news_row.fact.contradicts_json
    assert news_row.discredited_alibi is True
    assert news_row.discredited_by == "fact_court_toll"
    assert result.discredited_alibi_links["fact_news_alibi"] == "fact_court_toll"
    assert court_row.fact.contradicts_json == []


def test_cross_tier_police_affidavit_beats_news_report() -> None:
    news = _fact("fact_news", source_type="news_report", summary="Tabloid claims an alternate route.")
    aff = _fact("fact_aff", source_type="police_affidavit", summary="Affidavit GPS contradicts the tabloid route.")
    payload = {
        "conflict_groups": [{"fact_ids": ["fact_news", "fact_aff"], "alibi_fact_id": None, "discrediting_fact_id": None}]
    }
    client, _calls = _client(payload)
    result = ConflictReconciler(PROVIDERS, model_client=client).reconcile(_ledger(news, aff))
    news_row = next(item for item in result.facts if item.fact.fact_id == "fact_news")
    aff_row = next(item for item in result.facts if item.fact.fact_id == "fact_aff")
    assert "fact_aff" in news_row.fact.contradicts_json
    assert aff_row.fact.contradicts_json == []
    assert result.disputed_fact_ids == ()


def test_same_tier_conflict_keeps_both_marked_disputed() -> None:
    left = _fact("fact_court_a", source_type="court_ruling", summary="Witness A placed defendant at the shop.")
    right = _fact("fact_court_b", source_type="court_ruling", summary="Witness B placed defendant at the dock.")
    payload = {
        "conflict_groups": [{"fact_ids": ["fact_court_a", "fact_court_b"], "alibi_fact_id": None, "discrediting_fact_id": None}]
    }
    client, _calls = _client(payload)
    result = ConflictReconciler(PROVIDERS, model_client=client).reconcile(_ledger(left, right))
    assert result.disputed_fact_ids == ("fact_court_a", "fact_court_b")
    a_row = next(item for item in result.facts if item.fact.fact_id == "fact_court_a")
    b_row = next(item for item in result.facts if item.fact.fact_id == "fact_court_b")
    assert a_row.disputed and b_row.disputed
    assert "fact_court_b" in a_row.fact.contradicts_json
    assert "fact_court_a" in b_row.fact.contradicts_json


def test_discredited_alibi_links_to_discrediting_fact_same_tier() -> None:
    alibi = _fact(
        "fact_alibi",
        source_type="police_affidavit",
        summary="Defendant claimed he was at a cousin's apartment.",
    )
    discredit = _fact(
        "fact_receipt",
        source_type="police_affidavit",
        summary="A card receipt timestamped the defendant at a gas station.",
    )
    payload = {
        "conflict_groups": [
            {
                "fact_ids": ["fact_alibi", "fact_receipt"],
                "alibi_fact_id": "fact_alibi",
                "discrediting_fact_id": "fact_receipt",
            }
        ]
    }
    client, _calls = _client(payload)
    result = ConflictReconciler(PROVIDERS, model_client=client).reconcile(_ledger(alibi, discredit))
    alibi_row = next(item for item in result.facts if item.fact.fact_id == "fact_alibi")
    assert alibi_row.discredited_alibi is True
    assert alibi_row.discredited_by == "fact_receipt"
    assert "fact_receipt" in alibi_row.fact.contradicts_json
    assert result.disputed_fact_ids == ("fact_alibi", "fact_receipt")


def test_empty_conflicts_leave_ledger_untouched() -> None:
    fact = _fact("fact_only", source_type="court_ruling", summary="Only fact in the ledger.")
    client, _calls = _client({"conflict_groups": []})
    result = ConflictReconciler(PROVIDERS, model_client=client).reconcile(_ledger(fact))
    row = result.facts[0]
    assert row.fact.contradicts_json == []
    assert row.disputed is False
    assert result.disputed_fact_ids == ()


def test_reconciler_rejects_invented_fact_ids() -> None:
    fact = _fact("fact_real", source_type="court_ruling", summary="Real fact.")
    client, _calls = _client({"conflict_groups": [{"fact_ids": ["fact_real", "fact_fake"]}]})
    with pytest.raises(ConflictReconciliationError, match="unknown fact_id"):
        ConflictReconciler(PROVIDERS, model_client=client).reconcile(_ledger(fact))


def test_reconciler_is_tool_less_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    fact = _fact("fact_only", source_type="court_ruling", summary="Single fact.")
    client, _calls = _client({"conflict_groups": []})
    result = ConflictReconciler(PROVIDERS, model_client=client).reconcile(_ledger(fact))
    source = Path(sys.modules["agent2_evidence.conflict_reconciler"].__file__).read_text(encoding="utf-8")

    assert list(tmp_path.iterdir()) == []
    assert result.tools_enabled is False
    assert result.writes_database is False
    assert TOOLS_ENABLED is False
    assert WRITES_DATABASE is False
    assert MODEL_ID not in source
    for banned in (
        "import sqlite3",
        "import subprocess",
        "import socket",
        "import requests",
        "import httpx",
        "urllib.request",
    ):
        assert banned not in source