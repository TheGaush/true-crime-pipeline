"""Bounded cloud ASR slicer tests (Task 067 · offline, no ffmpeg)."""

from __future__ import annotations

from pathlib import Path

import pytest

from voice_sync.bounded_cloud_asr import (
    HARD_REJECT_DURATION_SEC,
    HARD_REJECT_SIZE_BYTES,
    MAX_CHUNK_DURATION_SEC,
    MAX_CHUNK_SIZE_BYTES,
    OUTPUT_SAMPLE_RATE_HZ,
    CloudAsrChunk,
    PayloadLimitExceededError,
    assert_chunk_within_slice_limits,
    estimate_flac_mono_16k_bytes,
    guard_before_transport,
    normalize_spoken_numbers,
    slice_transcoded_mono_16k,
    transcribe_foia_audio,
    write_synthetic_pcm_wav,
)


def test_normalize_spoken_year_2023() -> None:
    assert normalize_spoken_numbers("Incident in 2023 near county road") == (
        "Incident in twenty twenty three near county road"
    )


def test_estimate_flac_mono_16k_bytes_grows_with_duration() -> None:
    short = estimate_flac_mono_16k_bytes(10.0)
    long = estimate_flac_mono_16k_bytes(60.0)
    assert short < long
    assert estimate_flac_mono_16k_bytes(90.0) <= MAX_CHUNK_SIZE_BYTES


@pytest.fixture()
def three_minute_stereo_wav(tmp_path: Path) -> Path:
    wav_path = tmp_path / "foia_3min_48k_stereo.wav"
    write_synthetic_pcm_wav(
        wav_path,
        duration_sec=180.0,
        sample_rate_hz=48_000,
        channels=2,
    )
    return wav_path


def test_three_minute_48k_stereo_becomes_multiple_16k_mono_chunks(
    three_minute_stereo_wav: Path,
) -> None:
    seen: list[CloudAsrChunk] = []

    def _transport(chunk: CloudAsrChunk) -> str:
        seen.append(chunk)
        return f"ok-{chunk.index}"

    results = transcribe_foia_audio(
        three_minute_stereo_wav,
        _transport,
        transcript_hint="Recorded 2023",
    )
    assert len(results) >= 2
    assert len(seen) == len(results)
    total_duration = sum(c.duration_sec for c in seen)
    assert total_duration == pytest.approx(180.0, abs=0.05)
    for chunk in seen:
        assert chunk.sample_rate_hz == OUTPUT_SAMPLE_RATE_HZ
        assert chunk.channels == 1
        assert chunk.normalized_hint == "Recorded twenty twenty three"


def test_transport_never_receives_oversized_chunk(
    three_minute_stereo_wav: Path,
) -> None:
    delivered: list[CloudAsrChunk] = []

    transcribe_foia_audio(
        three_minute_stereo_wav,
        lambda chunk: delivered.append(chunk) or "x",
    )

    for chunk in delivered:
        assert chunk.duration_sec <= MAX_CHUNK_DURATION_SEC
        assert chunk.estimated_size_bytes <= MAX_CHUNK_SIZE_BYTES
        assert_chunk_within_slice_limits(chunk)


def test_hard_reject_blocks_transport_before_oversized_payload() -> None:
    oversize = CloudAsrChunk(
        index=0,
        start_sec=0.0,
        duration_sec=HARD_REJECT_DURATION_SEC + 0.5,
        flac_payload=b"x",
        estimated_size_bytes=1024,
    )
    called = False

    def _transport(_chunk: CloudAsrChunk) -> str:
        nonlocal called
        called = True
        return "nope"

    with pytest.raises(PayloadLimitExceededError):
        guard_before_transport(oversize)
        _transport(oversize)
    assert called is False


def test_hard_reject_oversize_bytes_before_transport() -> None:
    chunk = CloudAsrChunk(
        index=0,
        start_sec=0.0,
        duration_sec=30.0,
        flac_payload=bytes(HARD_REJECT_SIZE_BYTES + 1),
        estimated_size_bytes=HARD_REJECT_SIZE_BYTES + 1,
    )
    with pytest.raises(PayloadLimitExceededError):
        guard_before_transport(chunk)


def test_slice_respects_ninety_second_cap(tmp_path: Path) -> None:
    from voice_sync.bounded_cloud_asr import read_wav_source

    wav_path = tmp_path / "long.wav"
    write_synthetic_pcm_wav(wav_path, duration_sec=200.0, channels=2)

    source, pcm = read_wav_source(wav_path)
    chunks = slice_transcoded_mono_16k(source, pcm)
    assert len(chunks) >= 3
    for chunk in chunks:
        assert chunk.duration_sec <= MAX_CHUNK_DURATION_SEC + 1e-9
        assert chunk.estimated_size_bytes <= MAX_CHUNK_SIZE_BYTES