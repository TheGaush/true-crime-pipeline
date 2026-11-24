"""Task 069 — RMS amplitude envelope at 30 fps."""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

import pytest

from voice_sync.amplitude_envelope import (
    ENVELOPE_FPS,
    NOISE_GATE_DBFS,
    EnvelopeError,
    EnvelopeSegment,
    extract_amplitude_envelope,
    frame_start_ms,
    master_envelope_frame_count,
    quantize_envelope_sample,
    rms_dbfs,
    segment_frame_range,
    write_sine_wav,
)


class TestFrameCountInvariant:
    def test_round_total_master_ms(self) -> None:
        assert master_envelope_frame_count(6500) == 195
        assert master_envelope_frame_count(6550) == 197  # rounds 196.5 -> 197
        assert master_envelope_frame_count(0) == 0
        assert master_envelope_frame_count(33) == 1
        assert master_envelope_frame_count(17) == 1  # round(0.51) -> 1

    def test_master_length_matches_zero_to_total_range(self) -> None:
        total = 120_000
        assert master_envelope_frame_count(total) == segment_frame_range(0, total).stop


class TestSegmentFrameAlignment:
    def test_contiguous_narration_and_pad(self) -> None:
        narr = segment_frame_range(0, 4000)
        pad = segment_frame_range(4000, 4500)
        foia = segment_frame_range(4500, 6500)
        assert narr.stop == pad.start == 120
        assert pad.stop == foia.start == 135
        assert foia.stop == master_envelope_frame_count(6500)

    def test_fifteen_segments_partition_without_off_by_one(self) -> None:
        """Five beats × (NARRATION, TWIST_PAD, FOIA_AUDIO_SLOT) stress int-ms boundaries."""
        total = 0
        segments: list[tuple[str, int, int]] = []
        cursor = 0
        twist_pad = 523
        foia_len = 2841
        narr_lens = [3127, 4001, 2899, 5103, 3766]

        for narr_ms in narr_lens:
            segments.append(("NARRATION", cursor, cursor + narr_ms))
            cursor += narr_ms
            segments.append(("TWIST_PAD", cursor, cursor + twist_pad))
            cursor += twist_pad
            segments.append(("FOIA_AUDIO_SLOT", cursor, cursor + foia_len))
            cursor += foia_len
        total = cursor

        frame_count = master_envelope_frame_count(total)
        spans: list[range] = []
        for _, start, end in segments:
            span = segment_frame_range(start, end)
            spans.append(span)

        for prev, nxt in zip(spans, spans[1:]):
            assert prev.stop == nxt.start, f"gap or overlap at {prev.stop} vs {nxt.start}"

        assert spans[0].start == 0
        assert spans[-1].stop == frame_count
        assert len(spans) == 15
        assert sum(len(s) for s in spans) == frame_count

    def test_frame_starts_are_monotonic(self) -> None:
        total_frames = master_envelope_frame_count(65_550)
        for idx in range(1, total_frames):
            assert frame_start_ms(idx) >= frame_start_ms(idx - 1)


class TestNoiseGateAndQuantization:
    def test_below_gate_is_zero(self) -> None:
        quiet = rms_dbfs([0.001, -0.001, 0.0005])
        assert quantize_envelope_sample(quiet) == 0.0

    def test_at_gate_is_zero(self) -> None:
        assert quantize_envelope_sample(NOISE_GATE_DBFS) == 0.0

    def test_full_scale_near_one(self) -> None:
        loud = rms_dbfs([1.0, 0.95, -0.9])
        sample = quantize_envelope_sample(loud)
        assert 0.9 <= sample <= 1.0


class TestExtractAmplitudeEnvelope:
    def test_twist_pad_and_foia_stay_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "narr.wav"
            write_sine_wav(wav, duration_ms=4000, amplitude=0.4)
            segments = [
                EnvelopeSegment("NARRATION", 0, 4000, str(wav)),
                EnvelopeSegment("TWIST_PAD", 4000, 4500),
                EnvelopeSegment("FOIA_AUDIO_SLOT", 4500, 6500),
            ]
            env = extract_amplitude_envelope(6500, segments)
            assert len(env) == master_envelope_frame_count(6500)
            pad_frames = segment_frame_range(4000, 4500)
            foia_frames = segment_frame_range(4500, 6500)
            assert all(env[i] == 0.0 for i in pad_frames)
            assert all(env[i] == 0.0 for i in foia_frames)
            narr_frames = segment_frame_range(0, 4000)
            assert any(env[i] > 0.0 for i in narr_frames)

    def test_silent_narration_is_gated_to_zero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "quiet.wav"
            write_sine_wav(wav, duration_ms=2000, amplitude=1e-5)
            segments = [EnvelopeSegment("NARRATION", 0, 2000, str(wav))]
            env = extract_amplitude_envelope(2000, segments)
            assert all(v == 0.0 for v in env)

    def test_fifteen_segment_timeline_envelope_length(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cursor = 0
            twist_pad = 523
            foia_len = 2841
            narr_lens = [3127, 4001, 2899, 5103, 3766]
            envelope_segments: list[EnvelopeSegment] = []
            for idx, narr_ms in enumerate(narr_lens):
                wav = Path(tmp) / f"narr_{idx}.wav"
                write_sine_wav(
                    wav,
                    duration_ms=narr_ms,
                    amplitude=0.35,
                    frequency_hz=220.0 + idx * 17.0,
                )
                envelope_segments.append(
                    EnvelopeSegment("NARRATION", cursor, cursor + narr_ms, str(wav))
                )
                cursor += narr_ms
                envelope_segments.append(
                    EnvelopeSegment("TWIST_PAD", cursor, cursor + twist_pad)
                )
                cursor += twist_pad
                envelope_segments.append(
                    EnvelopeSegment("FOIA_AUDIO_SLOT", cursor, cursor + foia_len)
                )
                cursor += foia_len

            total = cursor
            env = extract_amplitude_envelope(total, envelope_segments)
            assert len(env) == master_envelope_frame_count(total)
            for kind, start, end in [
                (s.segment_kind, s.start_ms, s.end_ms) for s in envelope_segments
            ]:
                frames = segment_frame_range(start, end)
                if kind == "NARRATION":
                    assert any(env[i] > 0.0 for i in frames)
                else:
                    assert all(env[i] == 0.0 for i in frames)

    def test_rejects_overlapping_segments(self) -> None:
        segments = [
            EnvelopeSegment("NARRATION", 0, 3000, "missing.wav"),
            EnvelopeSegment("TWIST_PAD", 2500, 3200),
        ]
        with pytest.raises(EnvelopeError):
            extract_amplitude_envelope(3200, segments)

    def test_envelope_samples_are_two_decimal_bucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "narr.wav"
            write_sine_wav(wav, duration_ms=1000, amplitude=0.2)
            env = extract_amplitude_envelope(
                1000,
                [EnvelopeSegment("NARRATION", 0, 1000, str(wav))],
            )
            for value in env:
                assert value == round(value, 2)
                assert 0.0 <= value <= 1.0