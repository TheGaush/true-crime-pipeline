"""Offline tests for alias-expander@1."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from alias_expander import (  # noqa: E402
    CONTRACT_ID,
    DEFER_REASON_YOUTUBE_XRAY,
    MAX_ALIASES,
    AliasExpansionDeferred,
    AliasExpansionReady,
    CanonicalAliasExpander,
    CaseFacts,
    available_alias_slots,
    dedupe_queries,
    default_model_id,
    normalize_alias_query,
    title_has_person_or_place_name,
)

# Test fixture models the alias-expander@1 row from providers.yaml + DeepSeek role routing.
ALIAS_EXPANDER_PROVIDER_CONFIG = {
    "prompt_contracts": {
        CONTRACT_ID: {"model_id": "fixture-alias-expander-model"},
    },
    "providers": {
        "deepseek_chat": {
            "models": [
                {
                    "id": "DeepSeek-V4.1-Flash-1017",
                    "roles": ["scripting", "alias_expansion"],
                }
            ]
        }
    },
}


def _full_facts() -> CaseFacts:
    return CaseFacts(
        title="The John Rivera murder in Brownsville TX",
        suspect_full_name="John Rivera",
        incident_year="2018",
        victim_name="Maria Santos",
        crime_type="murder",
        city="Brownsville",
        case_nickname="Rivera bedroom case",
        forensic_detail="single 9mm casing on porch",
    )


def test_default_model_id_prefers_prompt_contract_entry():
    assert default_model_id(ALIAS_EXPANDER_PROVIDER_CONFIG) == "fixture-alias-expander-model"


def test_default_model_id_falls_back_to_alias_expansion_role():
    config = {
        "providers": {
            "deepseek_chat": {
                "models": [
                    {"id": "role-routed-model", "roles": ["alias_expansion"]},
                ]
            }
        }
    }
    assert default_model_id(config) == "role-routed-model"


def test_normalize_and_dedupe_queries():
    raw = [
        " John Rivera 2018!!! ",
        "john   rivera 2018",
        "Maria Santos murder",
        "Brownsville  Rivera bedroom case ",
        "single 9mm casing on porch",
        "extra fifth query",
    ]
    assert dedupe_queries(raw) == (
        "john rivera 2018",
        "maria santos murder",
        "brownsville rivera bedroom case",
        "single 9mm casing on porch",
    )
    assert len(dedupe_queries(raw)) == MAX_ALIASES
    assert normalize_alias_query("  Brownsville, TX!!  ") == "brownsville tx"


def test_title_clickbait_defers_without_llm_call():
    calls: list[tuple[str, str]] = []

    def fake_llm(model_id: str, prompt: str) -> str:
        calls.append((model_id, prompt))
        return "[]"

    expander = CanonicalAliasExpander(
        llm=fake_llm,
        provider_config=ALIAS_EXPANDER_PROVIDER_CONFIG,
    )
    outcome = expander.expand(
        CaseFacts(
            title="The DISTURBING Truth They Don't Want You To Know",
            suspect_full_name="John Rivera",
            incident_year="2018",
            victim_name="Maria Santos",
            crime_type="murder",
            city="Brownsville",
            case_nickname="Rivera bedroom case",
            forensic_detail="single 9mm casing on porch",
        )
    )

    assert isinstance(outcome, AliasExpansionDeferred)
    assert outcome.reason == DEFER_REASON_YOUTUBE_XRAY
    assert calls == []


def test_title_with_place_names_is_not_clickbait_only():
    assert title_has_person_or_place_name("What happened in Springfield County?")
    assert not title_has_person_or_place_name("Shocking unsolved mystery finally solved")


def test_expand_wraps_facts_in_data_envelope_and_caps_aliases():
    captured: list[str] = []

    def fake_llm(model_id: str, prompt: str) -> str:
        captured.append(prompt)
        assert model_id == "fixture-alias-expander-model"
        assert "<data>" in prompt and "</data>" in prompt
        payload = json.loads(prompt.split("<data>\n", 1)[1].rsplit("\n</data>", 1)[0])
        assert payload["canonical_slots"]["suspect_full_name_year"] == "John Rivera 2018"
        return json.dumps(
            [
                "John Rivera 2018",
                "Maria Santos murder",
                "Brownsville Rivera bedroom case",
                "single 9mm casing on porch",
                "Maria Santos murder!!!",  # duplicate after normalization
            ]
        )

    expander = CanonicalAliasExpander(
        llm=fake_llm,
        provider_config=ALIAS_EXPANDER_PROVIDER_CONFIG,
    )
    outcome = expander.expand(_full_facts())

    assert isinstance(outcome, AliasExpansionReady)
    assert outcome.model_id == "fixture-alias-expander-model"
    assert len(outcome.aliases) == 4
    assert outcome.aliases[0] == "john rivera 2018"
    assert captured


def test_omits_slots_with_missing_inputs():
    facts = CaseFacts(
        title="The Candace Hasek story in Mesa AZ",
        suspect_full_name="Candace Hasek",
        incident_year="2019",
        victim_name="Candace Hasek",
        crime_type="disappearance",
        city="Mesa",
        # no case nickname or forensic detail
    )
    slots = available_alias_slots(facts)
    assert set(slots) == {
        "suspect_full_name_year",
        "victim_name_crime",
    }

    def fake_llm(_model_id: str, prompt: str) -> str:
        payload = json.loads(prompt.split("<data>\n", 1)[1].rsplit("\n</data>", 1)[0])
        assert len(payload["canonical_slots"]) == 2
        return json.dumps(
            [
                "Candace Hasek 2019",
                "Candace Hasek disappearance",
            ]
        )

    outcome = CanonicalAliasExpander(
        llm=fake_llm,
        provider_config=ALIAS_EXPANDER_PROVIDER_CONFIG,
    ).expand(facts)

    assert isinstance(outcome, AliasExpansionReady)
    assert len(outcome.aliases) == 2


def test_explicit_model_id_overrides_provider_config():
    seen: list[str] = []

    def fake_llm(model_id: str, _prompt: str) -> str:
        seen.append(model_id)
        return json.dumps(["John Rivera 2018", "Maria Santos murder", "Brownsville case"])

    CanonicalAliasExpander(
        llm=fake_llm,
        provider_config=ALIAS_EXPANDER_PROVIDER_CONFIG,
        model_id="caller-selected-model",
    ).expand(_full_facts())

    assert seen == ["caller-selected-model"]