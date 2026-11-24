"""Task 070 — segmented voice timeline drift validator."""

from __future__ import annotations

import pytest

from voice_sync.drift_validator import (
    MAX_NARRATION_WAV_DRIFT_MS,
    DriftValidationError,
    TimelineSegment,
    assert_voice_timeline_drift,
    validate_voice_timeline_drift,
)


def _narration(
    segment_id: str,
    start_ms: int,
    end_ms: int,
    audio_path: str,
) -> TimelineSegment:
    return TimelineSegment(
        segment_id=segment_id,
        segment_kind="NARRATION",
        start_ms=start_ms,
        end_ms=end_ms,
        audio_path=audio_path,
    )


def _twist_pad(segment_id: str, start_ms: int, end_ms: int) -> TimelineSegment:
    return TimelineSegment(
        segment_id=segment_id,
        segment_kind="TWIST_PAD",
        start_ms=start_ms,
        end_ms=end_ms,
        audio_path=None,
    )


class TestTwentyMinuteSegmentedTimeline:
    def test_1_200_000_ms_many_segments_exact_sum_passes(self) -> None:
        total_master_ms = 1_200_000
        chunk_ms = 12_000
        segment_count = total_master_ms // chunk_ms
        segments: list[TimelineSegment] = []
        declared: dict[str, int] = {}
        cursor = 0

        for index in range(segment_count):
            if index % 11 == 10:
                duration = 600
                segments.append(
                    _twist_pad(f"pad_{index}", cursor, cursor + duration)
                )
                cursor += duration
                continue

            duration = chunk_ms - (600 if index % 11 == 9 else 0)
            if duration <= 0:
                duration = chunk_ms
            path = f"narration/chunk_{index:04d}.wav"
            segments.append(_narration(f"narr_{index}", cursor, cursor + duration, path))
            declared[path] = duration
            cursor += duration

        # Close any remainder with a final narration chunk.
        if cursor < total_master_ms:
            remainder = total_master_ms - cursor
            path = "narration/chunk_final.wav"
            segments.append(_narration("narr_final", cursor, cursor + remainder, path))
            declared[path] = remainder

        result = validate_voice_timeline_drift(
            total_master_ms=total_master_ms,
            segments=segments,
            declared_narration_wav_ms=declared,
        )
        assert result.ok
        assert result.segment_duration_sum_ms == total_master_ms
        assert not result.findings

    def test_uniform_10s_narration_grid_passes(self) -> None:
        total_master_ms = 1_200_000
        step = 10_000
        segments = [
            _narration(
                f"seg_{i}",
                i * step,
                (i + 1) * step,
                f"wav/{i:03d}.wav",
            )
            for i in range(total_master_ms // step)
        ]
        declared = {segment.audio_path: step for segment in segments}
        result = assert_voice_timeline_drift(
            total_master_ms=total_master_ms,
            segments=segments,
            declared_narration_wav_ms=declared,
        )
        assert result.ok


class TestNarrationWavDrift:
    def test_25_ms_mismatch_fails(self) -> None:
        segment = _narration("n1", 0, 5_000, "wav/a.wav")
        result = validate_voice_timeline_drift(
            total_master_ms=5_000,
            segments=[segment],
            declared_narration_wav_ms={"wav/a.wav": 5_025},
        )
        assert not result.ok
        assert any(f.code == "narration_wav_drift" for f in result.findings)
        assert 25 >= MAX_NARRATION_WAV_DRIFT_MS

    def test_19_ms_mismatch_passes(self) -> None:
        segment = _narration("n1", 0, 5_000, "wav/a.wav")
        result = validate_voice_timeline_drift(
            total_master_ms=5_000,
            segments=[segment],
            declared_narration_wav_ms={"wav/a.wav": 5_019},
        )
        assert result.ok

    def test_exact_match_passes(self) -> None:
        segment = _narration("n1", 100, 4_100, "wav/b.wav")
        result = validate_voice_timeline_drift(
            total_master_ms=4_000,
            segments=[segment],
            declared_narration_wav_ms={"wav/b.wav": 4_000},
        )
        assert result.ok


class TestTimelineSumInvariant:
    def test_segment_sum_mismatch_fails(self) -> None:
        segments = [
            _narration("n1", 0, 3_000, "wav/1.wav"),
            _twist_pad("p1", 3_000, 3_600),
        ]
        result = validate_voice_timeline_drift(
            total_master_ms=1_200_000,
            segments=segments,
            declared_narration_wav_ms={"wav/1.wav": 3_000},
        )
        assert not result.ok
        assert any(f.code == "timeline_sum_mismatch" for f in result.findings)

    def test_assert_raises_on_failure(self) -> None:
        with pytest.raises(DriftValidationError) as exc:
            assert_voice_timeline_drift(
                total_master_ms=1_000,
                segments=[_narration("n1", 0, 800, "wav/x.wav")],
                declared_narration_wav_ms={"wav/x.wav": 800},
            )
        assert exc.value.result.findings