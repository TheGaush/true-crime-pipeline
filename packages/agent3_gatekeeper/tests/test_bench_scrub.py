"""Tests for music-gated Demucs + PII scrub benchmark (Task 060)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BENCH_DIR = Path(__file__).resolve().parents[1] / "benchmarks"
sys.path.insert(0, str(_BENCH_DIR))

import bench_scrub  # noqa: E402

PEAK_RAM_CAP_GB = bench_scrub.PEAK_RAM_CAP_GB
BODYCAM_PRE_SLICE_PAD_S = bench_scrub.BODYCAM_PRE_SLICE_PAD_S
ScrubWindow = bench_scrub.ScrubWindow
SyntheticClipSpec = bench_scrub.SyntheticClipSpec
benchmark_music_gated_scrub = bench_scrub.benchmark_music_gated_scrub
estimate_unconditional_cost = bench_scrub.estimate_unconditional_cost
pre_slice_bodycam_windows = bench_scrub.pre_slice_bodycam_windows


def test_911_pure_speech_skips_demucs_and_beats_unconditional_cost() -> None:
    spec = SyntheticClipSpec(
        clip_id="foia_911_fixture",
        media_kind="call_911_wav",
        duration_s=45.0,
        music_detected=False,
        sample_rate_hz=8000,
        has_video_track=False,
    )
    result = benchmark_music_gated_scrub(spec)
    assert result.demucs_skipped is True
    assert result.demucs_applied is False
    assert result.music_detected is False
    assert result.demucs_audio_s == 0.0
    assert result.estimated_cost < result.unconditional_demucs_cost
    assert result.estimated_cost < estimate_unconditional_cost(spec)


def test_music_clip_applies_demucs() -> None:
    spec = SyntheticClipSpec(
        clip_id="foia_bodycam_music",
        media_kind="bodycam_mp4",
        duration_s=42.0,
        music_detected=True,
        visual_pii_boxes=2,
        sample_rate_hz=48000,
    )
    result = benchmark_music_gated_scrub(spec)
    assert result.demucs_skipped is False
    assert result.demucs_applied is True
    assert result.music_detected is True
    assert result.demucs_audio_s == pytest.approx(42.0)
    assert result.peak_ram_gb < PEAK_RAM_CAP_GB


@pytest.mark.parametrize("duration_s", [10.0, 30.0, 60.0])
def test_short_clips_peak_ram_stays_under_4gb(duration_s: float) -> None:
    spec = SyntheticClipSpec(
        clip_id=f"synth_{int(duration_s)}s",
        media_kind="interview_wav",
        duration_s=duration_s,
        music_detected=True,
        visual_pii_boxes=4,
        has_video_track=True,
    )
    result = benchmark_music_gated_scrub(spec)
    assert result.peak_ram_gb < PEAK_RAM_CAP_GB
    assert bench_scrub.ram_within_cap(result.peak_ram_gb)


def test_30min_bodycam_presliced_to_event_plus_minus_5s_before_demucs() -> None:
    duration_s = 30.0 * 60.0
    events = (300.0, 900.0, 1500.0)
    windows = pre_slice_bodycam_windows(duration_s, events, pad_s=BODYCAM_PRE_SLICE_PAD_S)
    assert windows == (
        ScrubWindow(295.0, 305.0),
        ScrubWindow(895.0, 905.0),
        ScrubWindow(1495.0, 1505.0),
    )

    spec = SyntheticClipSpec(
        clip_id="foia_long_bodycam",
        media_kind="bodycam_mp4",
        duration_s=duration_s,
        music_detected=True,
        event_timestamps_s=events,
        visual_pii_boxes=3,
    )
    result = benchmark_music_gated_scrub(spec)
    assert result.pre_slice_windows == windows
    assert result.demucs_audio_s == pytest.approx(30.0)
    assert result.demucs_applied is True
    assert result.demucs_audio_s < duration_s
    assert result.estimated_cost < result.unconditional_demucs_cost


def test_preslice_merges_overlapping_events() -> None:
    duration_s = 1800.0
    events = (100.0, 104.0)
    windows = pre_slice_bodycam_windows(duration_s, events, pad_s=5.0)
    assert windows == (ScrubWindow(95.0, 109.0),)


def test_non_music_speech_skips_demucs_without_911_bypass() -> None:
    spec = SyntheticClipSpec(
        clip_id="witness_interview",
        media_kind="interview_wav",
        duration_s=25.0,
        music_detected=False,
        sample_rate_hz=48000,
        has_video_track=False,
    )
    result = benchmark_music_gated_scrub(spec)
    assert result.demucs_skipped is True
    assert result.estimated_cost < estimate_unconditional_cost(spec)


def test_zero_duration_rejected() -> None:
    spec = SyntheticClipSpec(
        clip_id="bad",
        media_kind="interview_wav",
        duration_s=0.0,
    )
    with pytest.raises(ValueError, match="duration_s"):
        benchmark_music_gated_scrub(spec)