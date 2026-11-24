"""Tests for RULE_01 segmented timing and RULE_03 Flow beat splits (Task 076)."""

from __future__ import annotations

from agent4_director.linter_core import lint_manifest
from agent4_director.linter_types import LintScene, LintVoiceManifest, LintVoiceSegment
from agent4_director.rules.rule_01_03_timing import (
    RULE_01_TOLERANCE_MS,
    check_rule_01,
    check_rule_03,
    split_flow_beat_ms,
)

FOUR_MIN_MS = 4 * 60 * 1000


def test_split_flow_beat_9_2s_uses_6s_plus_3_2s() -> None:
    flow_ms, code_ms = split_flow_beat_ms(9200)
    assert flow_ms == 6000
    assert code_ms == 3200
    assert flow_ms + code_ms == 9200


def test_split_flow_beat_11_4s_uses_8s_plus_remainder() -> None:
    flow_ms, code_ms = split_flow_beat_ms(11_400)
    assert flow_ms == 8000
    assert code_ms == 3400
    assert code_ms / 1000.0 >= 2.5


def test_split_flow_beat_at_most_8_5s_is_unsplit() -> None:
    flow_ms, code_ms = split_flow_beat_ms(8500)
    assert flow_ms == 8500
    assert code_ms == 0


def test_rule_01_passes_when_scene_sum_within_tolerance() -> None:
    scenes = (
        LintScene("s1", "CODE_STICKMAN", 0, 60_000),
        LintScene("s2", "STILL_2K_PANZOOM", 60_000, 120_000),
    )
    voice = LintVoiceManifest(total_master_ms=120_000)
    assert check_rule_01(scenes, voice) == []


def test_rule_01_fails_when_scene_sum_exceeds_tolerance() -> None:
    scenes = (LintScene("s1", "CODE_STICKMAN", 0, 120_000),)
    voice = LintVoiceManifest(total_master_ms=119_600)
    findings = check_rule_01(scenes, voice)
    assert any(f.rule_id == "RULE_01" and "differs" in f.message for f in findings)


def test_rule_01_passes_at_exact_tolerance_boundary() -> None:
    total = 10_000
    scenes = (LintScene("s1", "CODE_STICKMAN", 0, total),)
    voice = LintVoiceManifest(total_master_ms=total - RULE_01_TOLERANCE_MS)
    assert check_rule_01(scenes, voice) == []


def test_rule_01_foia_scenes_align_with_foia_audio_slots() -> None:
    voice = LintVoiceManifest(
        total_master_ms=30_000,
        segments=(
            LintVoiceSegment("NARRATION", 0, 10_000),
            LintVoiceSegment("FOIA_AUDIO_SLOT", 10_000, 22_000, foia_asset_id="foia_a"),
            LintVoiceSegment("NARRATION", 22_000, 30_000),
        ),
    )
    scenes = (
        LintScene("n1", "CODE_STICKMAN", 0, 10_000),
        LintScene(
            "f1",
            "FOIA_REAL_FOOTAGE",
            10_000,
            22_000,
            foia_asset_id="foia_a",
        ),
        LintScene("n2", "CODE_STICKMAN", 22_000, 30_000),
    )
    assert check_rule_01(scenes, voice) == []
    report = lint_manifest(scenes, voice)
    assert report.passed


def test_rule_01_four_minute_foia_timeline_alignment() -> None:
    """4-minute segmented voice track with multiple FOIA slots and matching scenes."""
    slot_specs = (
        ("foia_1", 45_000, 105_000),
        ("foia_2", 105_000, 165_000),
        ("foia_3", 165_000, 210_000),
    )
    segments: list[LintVoiceSegment] = [
        LintVoiceSegment("NARRATION", 0, 45_000),
    ]
    for asset, start, end in slot_specs:
        segments.append(
            LintVoiceSegment("FOIA_AUDIO_SLOT", start, end, foia_asset_id=asset)
        )
    segments.append(LintVoiceSegment("NARRATION", 210_000, FOUR_MIN_MS))

    voice = LintVoiceManifest(total_master_ms=FOUR_MIN_MS, segments=tuple(segments))

    scenes: list[LintScene] = [
        LintScene("open", "CODE_STICKMAN", 0, 45_000),
    ]
    for asset, start, end in slot_specs:
        engine = "AUDIO_EVIDENCE_CARD" if asset == "foia_2" else "FOIA_REAL_FOOTAGE"
        scenes.append(
            LintScene(
                f"scene_{asset}",
                engine,
                start,
                end,
                foia_asset_id=asset,
            )
        )
    scenes.append(LintScene("close", "CODE_STICKMAN", 210_000, FOUR_MIN_MS))

    assert check_rule_01(tuple(scenes), voice) == []
    report = lint_manifest(tuple(scenes), voice)
    assert report.passed


def test_rule_03_flags_unsplit_long_flow_beat() -> None:
    scenes = (LintScene("hero", "FLOW_HERO_VIDEO", 0, 9200),)
    findings = check_rule_03(scenes)
    assert len(findings) == 1
    assert findings[0].rule_id == "RULE_03"
    assert findings[0].context["proposed_flow_ms"] == 6000
    assert findings[0].context["proposed_code_ms"] == 3200


def test_rule_03_allows_short_flow_beats() -> None:
    scenes = (LintScene("hero", "FLOW_HERO_VIDEO", 0, 8000),)
    assert check_rule_03(scenes) == []