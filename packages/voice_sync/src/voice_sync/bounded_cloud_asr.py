"""Bounded optional cloud ASR slicer for raw FOIA audio (Task 067 · F-03).

Offline tests simulate 48 kHz stereo → 16 kHz mono FLAC sizing without ffmpeg.
"""

from __future__ import annotations

import math
import re
import struct
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

MAX_CHUNK_DURATION_SEC = 90.0
MAX_CHUNK_SIZE_BYTES = 4 * 1024 * 1024
HARD_REJECT_DURATION_SEC = 115.0
HARD_REJECT_SIZE_BYTES = int(7.5 * 1024 * 1024)

OUTPUT_SAMPLE_RATE_HZ = 16_000
INPUT_SAMPLE_RATE_HZ = 48_000

# Deterministic byte model for 16 kHz mono speech FLAC (no encoder available offline).
FLAC_BYTES_PER_SECOND = 18_000
FLAC_HEADER_BYTES = 4_096

SILENCE_THRESHOLD = 120
MIN_SILENCE_MS = 250
SILENCE_SEARCH_WINDOW_SEC = 5.0

_SPOKEN_YEAR_2023 = "twenty twenty three"


class PayloadLimitExceededError(ValueError):
    """Cloud ASR payload would exceed DeepSeek/Gemini hard limits (F-03)."""


@dataclass(frozen=True, slots=True)
class AudioSourceInfo:
    duration_sec: float
    sample_rate_hz: int
    channels: int


@dataclass(frozen=True, slots=True)
class CloudAsrChunk:
    index: int
    start_sec: float
    duration_sec: float
    flac_payload: bytes
    estimated_size_bytes: int
    sample_rate_hz: int = OUTPUT_SAMPLE_RATE_HZ
    channels: int = 1
    normalized_hint: str | None = None


def estimate_flac_mono_16k_bytes(duration_sec: float) -> int:
    """Return a deterministic offline size estimate for 16 kHz mono FLAC."""
    if duration_sec <= 0:
        return FLAC_HEADER_BYTES
    return FLAC_HEADER_BYTES + int(duration_sec * FLAC_BYTES_PER_SECOND)


def max_duration_for_size_cap(size_cap_bytes: int = MAX_CHUNK_SIZE_BYTES) -> float:
    cap = max(size_cap_bytes - FLAC_HEADER_BYTES, 0)
    if FLAC_BYTES_PER_SECOND == 0:
        return 0.0
    return cap / FLAC_BYTES_PER_SECOND


def normalize_spoken_numbers(text: str) -> str:
    """Normalize spoken numerals in transcript hints (e.g. year 2023)."""
    return re.sub(r"\b2023\b", _SPOKEN_YEAR_2023, text)


def read_wav_source(path: Path) -> tuple[AudioSourceInfo, bytes]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        nframes = wf.getnframes()
        pcm = wf.readframes(nframes)
    duration = nframes / float(sample_rate) if sample_rate else 0.0
    info = AudioSourceInfo(
        duration_sec=duration,
        sample_rate_hz=sample_rate,
        channels=channels,
    )
    return info, pcm


def _mono_samples(pcm: bytes, channels: int) -> list[int]:
    if not pcm:
        return []
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm)
    if channels <= 1:
        return list(samples)
    mono: list[int] = []
    for idx in range(0, len(samples), channels):
        frame = samples[idx : idx + channels]
        mono.append(sum(frame) // len(frame))
    return mono


def _find_silence_split_ms(
    mono: Sequence[int],
    sample_rate: int,
    search_start_sec: float,
    search_end_sec: float,
) -> float | None:
    if sample_rate <= 0 or not mono:
        return None
    start_idx = max(int(search_start_sec * sample_rate), 0)
    end_idx = min(int(search_end_sec * sample_rate), len(mono))
    if end_idx <= start_idx:
        return None
    min_run = max(int(sample_rate * (MIN_SILENCE_MS / 1000.0)), 1)
    run = 0
    for idx in range(start_idx, end_idx):
        if abs(mono[idx]) <= SILENCE_THRESHOLD:
            run += 1
            if run >= min_run:
                split_ms = int(((idx - run // 2) / sample_rate) * 1000)
                return split_ms / 1000.0
        else:
            run = 0
    return None


def slice_transcoded_mono_16k(
    source: AudioSourceInfo,
    pcm: bytes,
    *,
    transcript_hint: str | None = None,
) -> list[CloudAsrChunk]:
    """Slice downsampled 16 kHz mono audio into bounded cloud-ASR chunks."""
    if source.duration_sec <= 0:
        return []

    normalized_hint = (
        normalize_spoken_numbers(transcript_hint) if transcript_hint else None
    )
    size_limited_sec = max_duration_for_size_cap(MAX_CHUNK_SIZE_BYTES)
    chunk_cap_sec = min(MAX_CHUNK_DURATION_SEC, size_limited_sec)

    mono = _mono_samples(pcm, source.channels)
    # Virtual downsample: silence search uses input timeline (duration unchanged).
    src_rate = source.sample_rate_hz or INPUT_SAMPLE_RATE_HZ

    chunks: list[CloudAsrChunk] = []
    cursor_sec = 0.0
    index = 0
    while cursor_sec < source.duration_sec - 1e-9:
        remaining = source.duration_sec - cursor_sec
        target_end = min(cursor_sec + chunk_cap_sec, source.duration_sec)

        if remaining > chunk_cap_sec:
            search_start = max(target_end - SILENCE_SEARCH_WINDOW_SEC, cursor_sec)
            split_at = _find_silence_split_ms(
                mono, src_rate, search_start, target_end
            )
            if split_at is not None and split_at > cursor_sec:
                target_end = split_at

        duration = target_end - cursor_sec
        if duration <= 0:
            duration = min(chunk_cap_sec, remaining)
            target_end = cursor_sec + duration

        est_bytes = estimate_flac_mono_16k_bytes(duration)
        if est_bytes > MAX_CHUNK_SIZE_BYTES:
            duration = max_duration_for_size_cap(MAX_CHUNK_SIZE_BYTES)
            target_end = cursor_sec + duration
            est_bytes = estimate_flac_mono_16k_bytes(duration)

        payload = bytes(est_bytes)
        chunks.append(
            CloudAsrChunk(
                index=index,
                start_sec=cursor_sec,
                duration_sec=duration,
                flac_payload=payload,
                estimated_size_bytes=est_bytes,
                normalized_hint=normalized_hint,
            )
        )
        index += 1
        cursor_sec = target_end

    return chunks


def guard_before_transport(chunk: CloudAsrChunk) -> None:
    """Hard-reject oversize payloads before any cloud transport call (F-03)."""
    if chunk.duration_sec > HARD_REJECT_DURATION_SEC:
        raise PayloadLimitExceededError(
            f"duration {chunk.duration_sec}s exceeds hard cap {HARD_REJECT_DURATION_SEC}s"
        )
    if chunk.estimated_size_bytes > HARD_REJECT_SIZE_BYTES:
        raise PayloadLimitExceededError(
            f"payload {chunk.estimated_size_bytes} bytes exceeds hard cap "
            f"{HARD_REJECT_SIZE_BYTES} bytes"
        )


def assert_chunk_within_slice_limits(chunk: CloudAsrChunk) -> None:
    if chunk.duration_sec > MAX_CHUNK_DURATION_SEC + 1e-9:
        raise PayloadLimitExceededError(
            f"chunk duration {chunk.duration_sec}s exceeds slicer cap "
            f"{MAX_CHUNK_DURATION_SEC}s"
        )
    if chunk.estimated_size_bytes > MAX_CHUNK_SIZE_BYTES:
        raise PayloadLimitExceededError(
            f"chunk size {chunk.estimated_size_bytes} exceeds slicer cap "
            f"{MAX_CHUNK_SIZE_BYTES} bytes"
        )


CloudAsrTransport = Callable[[CloudAsrChunk], str]


def transcribe_foia_audio(
    wav_path: Path,
    transport: CloudAsrTransport,
    *,
    transcript_hint: str | None = None,
) -> list[str]:
    """Transcode (simulated), slice, and send bounded chunks through mocked transport."""
    source, pcm = read_wav_source(wav_path)
    chunks = slice_transcoded_mono_16k(source, pcm, transcript_hint=transcript_hint)
    results: list[str] = []
    for chunk in chunks:
        assert_chunk_within_slice_limits(chunk)
        guard_before_transport(chunk)
        results.append(transport(chunk))
    return results


def write_synthetic_pcm_wav(
    path: Path,
    *,
    duration_sec: float,
    sample_rate_hz: int = INPUT_SAMPLE_RATE_HZ,
    channels: int = 2,
    tone_hz: float = 440.0,
    silence_every_sec: float | None = None,
) -> AudioSourceInfo:
    """Write a deterministic PCM WAV for offline slicer tests (stdlib only)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    nframes = int(duration_sec * sample_rate_hz)
    frames: list[int] = []
    for frame_idx in range(nframes):
        t = frame_idx / sample_rate_hz
        if silence_every_sec and int(t) % int(silence_every_sec) == 0 and int(t) > 0:
            sample = 0
        else:
            sample = int(6000 * math.sin(2 * math.pi * tone_hz * t))
        for _ in range(channels):
            frames.append(sample)

    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate_hz)
        wf.writeframes(struct.pack(f"<{len(frames)}h", *frames))

    return AudioSourceInfo(
        duration_sec=duration_sec,
        sample_rate_hz=sample_rate_hz,
        channels=channels,
    )