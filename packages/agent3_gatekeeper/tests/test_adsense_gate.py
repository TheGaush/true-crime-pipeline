"""Tests for first-30s AdSense safety gate."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from agent3_gatekeeper.adsense_gate import (
    EPISODE_INTRO_END_MS,
    AdSenseGateResult,
    FoiaIntroSlice,
    First30sAdSenseGate,
    evaluate_first_30s_adsense_safe,
    find_weapon_terms,
    profanity_overlaps_source_window,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "adsense_gate.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}

CLEAN_OPENING = (
    "A county records request opened a cold case file. "
    "Investigators reviewed timelines without graphic detail."
)

_BODYMAP_PROFANITY = [
    {"start_ms": 42_000, "end_ms": 43_500, "severity": "severe"},
]


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


def test_clean_opening_narration_passes() -> None:
    result = evaluate_first_30s_adsense_safe(CLEAN_OPENING)
    assert isinstance(result, AdSenseGateResult)
    assert result.first_30s_adsense_safe == 1
    assert result.passed is True
    assert result.to_audit_fields()["first_30s_adsense_safe"] == 1


def test_narration_profanity_fails_gate() -> None:
    result = evaluate_first_30s_adsense_safe("The dispatcher said damn it on tape.")
    assert result.first_30s_adsense_safe == 0
    assert result.passed is False
    assert any("profanity" in v for v in result.violations)


def test_narration_weapon_term_fails_gate() -> None:
    result = evaluate_first_30s_adsense_safe("Officers recovered a handgun from the scene.")
    assert result.first_30s_adsense_safe == 0
    assert any("weapon" in v for v in result.violations)


def test_cinematography_shooting_tracking_shot_allowed() -> None:
    text = "We open on a shooting tracking shot across the evidence board."
    assert find_weapon_terms(text) == []
    result = evaluate_first_30s_adsense_safe(text)
    assert result.first_30s_adsense_safe == 1


def test_graphic_distress_tag_on_foia_slice_fails() -> None:
    slice_ = FoiaIntroSlice(
        foia_asset_id="foia_bodycam",
        source_start_ms=0,
        source_end_ms=8_000,
        episode_start_ms=0,
        episode_end_ms=12_000,
        graphic_distress_tags=["GORE_VISIBLE"],
    )
    result = evaluate_first_30s_adsense_safe(CLEAN_OPENING, foia_intro_slices=[slice_])
    assert result.first_30s_adsense_safe == 0
    assert any("graphic_distress_tag" in v for v in result.violations)


def test_foia_profanity_overlap_40000_52000_fails_gate() -> None:
    """Acceptance: 42s profanity inside source 40s–52s mapped to cold open fails."""
    cold_open = FoiaIntroSlice(
        foia_asset_id="case_golden_bodycam",
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=0,
        episode_end_ms=EPISODE_INTRO_END_MS,
        profanity_intervals_json=_BODYMAP_PROFANITY,
    )
    overlaps = profanity_overlaps_source_window(
        _BODYMAP_PROFANITY,
        40_000,
        52_000,
    )
    assert len(overlaps) == 1
    assert overlaps[0]["start_ms"] == 42_000

    result = First30sAdSenseGate().evaluate(CLEAN_OPENING, foia_intro_slices=[cold_open])
    assert result.first_30s_adsense_safe == 0
    assert result.passed is False
    assert any("profanity_interval:42000-43500" in v for v in result.violations)


def test_foia_profanity_outside_source_window_passes() -> None:
    cold_open = FoiaIntroSlice(
        foia_asset_id="case_golden_bodycam",
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=0,
        episode_end_ms=EPISODE_INTRO_END_MS,
        profanity_intervals_json=[{"start_ms": 60_000, "end_ms": 61_000, "severity": "severe"}],
    )
    result = evaluate_first_30s_adsense_safe(CLEAN_OPENING, foia_intro_slices=[cold_open])
    assert result.first_30s_adsense_safe == 1


def test_intro_slice_after_thirty_seconds_ignored() -> None:
    later = FoiaIntroSlice(
        foia_asset_id="foia_late",
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=EPISODE_INTRO_END_MS + 1,
        episode_end_ms=EPISODE_INTRO_END_MS + 15_000,
        profanity_intervals_json=_BODYMAP_PROFANITY,
        graphic_distress_tags=["GORE_VISIBLE"],
    )
    result = evaluate_first_30s_adsense_safe(CLEAN_OPENING, foia_intro_slices=[later])
    assert result.first_30s_adsense_safe == 1


@pytest.mark.parametrize(
    "json_payload",
    [
        _BODYMAP_PROFANITY,
        '[{"start_ms":42000,"end_ms":43500,"severity":"severe"}]',
    ],
)
def test_profanity_json_string_and_list_equivalent(json_payload) -> None:
    overlaps = profanity_overlaps_source_window(json_payload, 40_000, 52_000)
    assert len(overlaps) == 1