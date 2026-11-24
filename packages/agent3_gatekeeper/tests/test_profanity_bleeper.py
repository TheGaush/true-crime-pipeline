"""Whole-clip profanity map and cold-open slice auto-bleeper tests.

ASR word timestamps are injected. No network and no live ASR.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from agent3_gatekeeper.profanity_bleeper import (
    BLEEP_HZ,
    EPISODE_INTRO_END_MS,
    SEVERE,
    FoiaTimelineSlice,
    ProfanityInterval,
    WholeClipProfanityMapper,
    WordTimestamp,
    plan_bleeps,
    profanity_in_intro_window,
    scan_whole_clip,
    serialize_profanity_intervals,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "agent3_gatekeeper"
    / "profanity_bleeper.py"
)
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}
_BODYCAM_DURATION_MS = 600_000
_BODYCAM_042_EXPLICIT = WordTimestamp(word="fuck", start_ms=42_000, end_ms=43_500)
_LATE_MODERATE = WordTimestamp(word="damn", start_ms=590_000, end_ms=590_400)


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


def test_whole_clip_scan_indexes_profanity_at_42s() -> None:
    """10-minute bodycam: 0:42 expletive is indexed on the source timeline."""
    result = scan_whole_clip([_BODYCAM_042_EXPLICIT], _BODYCAM_DURATION_MS)
    assert len(result.intervals) == 1
    hit = result.intervals[0]
    assert hit.start_ms == 42_000
    assert hit.end_ms == 43_500
    assert hit.severity == SEVERE
    assert result.profanity_intervals_json == [
        {"start_ms": 42_000, "end_ms": 43_500, "severity": SEVERE},
    ]


def test_scan_is_not_capped_at_first_15_seconds() -> None:
    """Regression: profanity after 15s must still be indexed on a whole-clip scan."""
    late = WordTimestamp(word="damn", start_ms=16_000, end_ms=16_400)
    full = scan_whole_clip([late], 60_000)
    capped = scan_whole_clip([late], 60_000, scan_cap_ms=15_000)
    assert len(full.intervals) == 1
    assert full.intervals[0].start_ms == 16_000
    assert len(capped.intervals) == 0


def test_cold_open_slice_bleeps_042_profanity() -> None:
    """Slice 0:40-0:52 mapped to episode 0:00-0:30 must bleep the 0:42 expletive."""
    scan = scan_whole_clip([_BODYCAM_042_EXPLICIT], _BODYCAM_DURATION_MS)
    cold_open = FoiaTimelineSlice(
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=0,
        episode_end_ms=12_000,
    )
    bleeps = plan_bleeps(scan.intervals, [cold_open])
    assert len(bleeps) == 1
    bleep = bleeps[0]
    assert bleep.source_start_ms == 42_000
    assert bleep.bleep_hz == BLEEP_HZ
    assert bleep.mute is True
    assert bleep.episode_start_ms == pytest.approx(2_000, abs=50)
    assert bleep.reason in {"severe_everywhere", "intro_slice"}
    assert profanity_in_intro_window(scan.intervals, [cold_open]) == []


def test_user_scenario_slice_40000_52000_cold_open() -> None:
    """Explicit acceptance case: 42000 ms profanity inside 40000-52000 -> intro bleep."""
    interval = ProfanityInterval(start_ms=42_000, end_ms=43_500, severity=SEVERE)
    slice_ = FoiaTimelineSlice(
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=0,
        episode_end_ms=30_000,
    )
    bleeps = plan_bleeps([interval], [slice_])
    assert any(b.source_start_ms == 42_000 for b in bleeps)
    assert all(b.bleep_hz == BLEEP_HZ and b.mute for b in bleeps)


def test_ten_minute_profanity_indexed_not_forced_into_intro() -> None:
    """Moderate profanity at 10:00 is indexed but not auto-bleeped in a non-intro slice."""
    scan = scan_whole_clip(
        [_BODYCAM_042_EXPLICIT, _LATE_MODERATE],
        _BODYCAM_DURATION_MS,
    )
    assert len(scan.intervals) == 2
    late_only = [i for i in scan.intervals if i.start_ms == 590_000]
    assert len(late_only) == 1
    assert late_only[0].severity == "moderate"

    body_slice = FoiaTimelineSlice(
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=0,
        episode_end_ms=12_000,
    )
    late_slice = FoiaTimelineSlice(
        source_start_ms=590_000,
        source_end_ms=610_000,
        episode_start_ms=600_000,
        episode_end_ms=620_000,
    )
    bleeps = plan_bleeps(scan.intervals, [body_slice, late_slice])
    assert any(b.source_start_ms == 42_000 for b in bleeps)
    assert not any(b.source_start_ms == 590_000 for b in bleeps)


def test_severe_bleeps_on_non_intro_placement() -> None:
    """Severe slurs are bleeped even when the slice sits after 0:30 on the episode."""
    severe = ProfanityInterval(start_ms=50_000, end_ms=51_000, severity=SEVERE)
    later = FoiaTimelineSlice(
        source_start_ms=48_000,
        source_end_ms=55_000,
        episode_start_ms=120_000,
        episode_end_ms=127_000,
    )
    bleeps = plan_bleeps([severe], [later])
    assert len(bleeps) == 1
    assert bleeps[0].reason == "severe_everywhere"
    assert bleeps[0].episode_start_ms > EPISODE_INTRO_END_MS


def test_moderate_in_intro_slice_requires_overlap() -> None:
    moderate = ProfanityInterval(start_ms=41_500, end_ms=42_000, severity="moderate")
    intro_slice = FoiaTimelineSlice(
        source_start_ms=40_000,
        source_end_ms=52_000,
        episode_start_ms=0,
        episode_end_ms=30_000,
    )
    bleeps = plan_bleeps([moderate], [intro_slice])
    assert len(bleeps) == 1
    assert bleeps[0].reason == "intro_slice"


def test_serialize_profanity_intervals_round_trip() -> None:
    payload = serialize_profanity_intervals(
        [ProfanityInterval(42_000, 43_500, SEVERE)],
    )
    assert json.loads(payload) == [
        {"start_ms": 42_000, "end_ms": 43_500, "severity": SEVERE},
    ]


def test_mapper_facade_with_injected_provider() -> None:
    def provider() -> list[WordTimestamp]:
        return [_BODYCAM_042_EXPLICIT]

    mapper = WholeClipProfanityMapper(word_timestamps_provider=provider)
    scan = mapper.scan(_BODYCAM_DURATION_MS)
    cold_open = FoiaTimelineSlice(40_000, 52_000, 0, 12_000)
    bleeps = mapper.plan(scan, [cold_open])
    assert scan.intervals[0].start_ms == 42_000
    assert bleeps[0].source_start_ms == 42_000