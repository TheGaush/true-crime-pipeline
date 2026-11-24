"""Tests for CaseBible lock and Flow keyframe palette routing."""

from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError
from shared_contracts.models import CaseBible, CharacterSpec, StyleDna

from agent4_director.case_bible import (
    DEFAULT_FLOW_KEYFRAME_SAFE_PALETTE,
    EVIDENCE_CRIMSON_HEX,
    INK_HEX,
    MUTED_SLATE_HEX,
    WARM_AMBER_HEX,
    ColorChannel,
    build_style_dna,
    default_characters,
    flow_palette_excludes_crimson,
    load_case_bible,
    lock_case_bible,
    overlay_callout_hex,
    persist_case_bible,
    resolve_character_color_for_flow,
    resolve_hex,
)

_VECTOR_BIBLE_PAYLOAD = {
    "episode_id": "ep_0",
    "style_dna_json": {"flow_keyframe_safe_palette": list(DEFAULT_FLOW_KEYFRAME_SAFE_PALETTE)},
    "characters_json": [
        {"character_id": "detective_01", "prop": "notepad", "color_hex": MUTED_SLATE_HEX},
        {"character_id": "suspect_01", "prop": "coat", "color_hex": WARM_AMBER_HEX},
    ],
    "locked_at": 500,
}


def test_lock_case_bible_matches_shared_contract_vector() -> None:
    bible = lock_case_bible("ep_0", locked_at=500)
    canonical = CaseBible.model_validate(_VECTOR_BIBLE_PAYLOAD)
    assert bible.model_dump() == canonical.model_dump()


def test_flow_palette_excludes_evidence_crimson() -> None:
    style = build_style_dna()
    assert flow_palette_excludes_crimson(style)
    assert EVIDENCE_CRIMSON_HEX not in style.flow_keyframe_safe_palette
    with pytest.raises(ValidationError):
        build_style_dna(flow_keyframe_safe_palette=[EVIDENCE_CRIMSON_HEX, INK_HEX])


def test_overlay_callout_retains_crimson() -> None:
    style = build_style_dna()
    assert overlay_callout_hex(style) == EVIDENCE_CRIMSON_HEX
    resolution = resolve_hex(
        style,
        EVIDENCE_CRIMSON_HEX,
        channel=ColorChannel.REMOTION_OVERLAY,
    )
    assert resolution.resolved_hex.upper() == EVIDENCE_CRIMSON_HEX
    assert resolution.substituted is False


def test_suspect_crimson_substituted_for_flow_start_png() -> None:
    suspect_crimson = CharacterSpec(
        character_id="suspect_01",
        prop="badge",
        color_hex=EVIDENCE_CRIMSON_HEX,
    )
    bible = lock_case_bible(
        "ep_crimson_edge",
        characters=[default_characters()[0], suspect_crimson],
        locked_at=1_700_000_000,
    )
    flow_color = resolve_character_color_for_flow(bible, "suspect_01")
    assert flow_color.substituted is True
    assert flow_color.resolved_hex.upper() == WARM_AMBER_HEX
    assert flow_color.resolved_hex.upper() != EVIDENCE_CRIMSON_HEX
    overlay = resolve_hex(
        bible.style_dna_json,
        suspect_crimson.color_hex,
        channel=ColorChannel.STILL_2K_CALLOUT,
    )
    assert overlay.resolved_hex.upper() == EVIDENCE_CRIMSON_HEX


def test_detective_flow_color_unchanged_when_palette_safe() -> None:
    bible = lock_case_bible("ep_flow", locked_at=42)
    flow_color = resolve_character_color_for_flow(bible, "detective_01")
    assert flow_color.resolved_hex == MUTED_SLATE_HEX
    assert flow_color.substituted is False


def test_sqlite_round_trip_case_bible() -> None:
    bible = lock_case_bible("ep_sqlite", locked_at=900)
    connection = sqlite3.connect(":memory:")
    try:
        persist_case_bible(connection, bible)
        loaded = load_case_bible(connection, "ep_sqlite")
        assert loaded is not None
        assert loaded.model_dump() == bible.model_dump()
    finally:
        connection.close()


def test_default_characters_register_detective_and_suspect() -> None:
    ids = {character.character_id for character in default_characters()}
    assert ids == {"detective_01", "suspect_01"}