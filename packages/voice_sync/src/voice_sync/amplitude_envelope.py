"""RMS vocal amplitude envelope at 30 fps for VoiceTrackManifest (Task 069)."""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

ENVELOPE_FPS = 30
NOISE_GATE_DBFS = -50.0
DEFAULT_SAMPLE_RATE = 48_000

SegmentKind = Literal["NARRATION", "TWIST_PAD", "FOIA_AUDIO_SLOT"]


class EnvelopeError(ValueError):
    """Invalid envelope inputs or WAV read failure."""


@dataclass(frozen=True, slots=True)
class EnvelopeSegment:
    segment_kind: SegmentKind
    start_ms: int
    end_ms: int
    audio_path: str | None = None


def master_envelope_frame_count(total_master_ms: int) -> int:
    """``round(total_master_ms * 30 / 1000)`` using integer milliseconds only."""
    if total_master_ms < 0:
        raise EnvelopeError("total_master_ms must be >= 0")
    return (total_master_ms * ENVELOPE_FPS + 500) // 1000


def frame_start_ms(frame_index: int) -> int:
    if frame_index < 0:
        raise EnvelopeError("frame_index must be >= 0")
    return (frame_index * 1000) // ENVELOPE_FPS


def segment_frame_range(start_ms: int, end_ms: int) -> range:
    """Half-open frame indices for voice segment ``[start_ms, end_ms)`` (integer ms)."""
    if end_ms < start_ms:
        raise EnvelopeError("end_ms must be >= start_ms")
    first = (start_ms * ENVELOPE_FPS) // 1000
    last = (end_ms * ENVELOPE_FPS) // 1000
    return range(first, last)


def rms_dbfs(samples: Sequence[float]) -> float:
    if not samples:
        return float("-inf")
    mean_sq = sum(s * s for s in samples) / len(samples)
    rms = math.sqrt(mean_sq)
    if rms <= 0.0:
        return float("-inf")
    return 20.0 * math.log10(rms)


def quantize_envelope_sample(dbfs: float, *, gate_dbfs: float = NOISE_GATE_DBFS) -> float:
    """Map RMS dBFS to ``[0.00, 1.00]`` with a noise gate."""
    if dbfs <= gate_dbfs or dbfs == float("-inf") or math.isinf(dbfs):
        return 0.0
    linear = 10.0 ** (dbfs / 20.0)
    gate_linear = 10.0 ** (gate_dbfs / 20.0)
    span = 1.0 - gate_linear
    if span <= 0.0:
        return 0.0
    scaled = (linear - gate_linear) / span
    return round(max(0.0, min(1.0, scaled)), 2)


def read_wav_mono_float(path: str | Path) -> tuple[list[float], int]:
    """Read WAV into normalized mono floats (stereo averaged)."""
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    if width != 2:
        raise EnvelopeError(f"unsupported sample width {width} in {path}")
    count = len(raw) // 2
    ints = struct.unpack(f"<{count}h", raw)
    if channels == 1:
        samples = [v / 32768.0 for v in ints]
    else:
        samples = []
        for i in range(0, len(ints), channels):
            frame = ints[i : i + channels]
            samples.append(sum(v / 32768.0 for v in frame) / len(frame))
    return samples, rate


def write_sine_wav(
    path: str | Path,
    *,
    duration_ms: int,
    frequency_hz: float = 440.0,
    amplitude: float = 0.25,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> None:
    """Write mono 16-bit PCM sine (test helper, no scipy)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = duration_ms * sample_rate // 1000
    pcm = bytearray()
    for i in range(frame_count):
        t = i / sample_rate
        sample = amplitude * math.sin(2.0 * math.pi * frequency_hz * t)
        pcm.extend(struct.pack("<h", int(round(max(-1.0, min(1.0, sample)) * 32767.0))))
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes(pcm))


def _samples_for_master_window(
    mono: Sequence[float],
    sample_rate: int,
    segment_start_ms: int,
    window_start_ms: int,
    window_end_ms: int,
) -> list[float]:
    rel_start = window_start_ms - segment_start_ms
    rel_end = window_end_ms - segment_start_ms
    if rel_end <= rel_start:
        return []
    i0 = rel_start * sample_rate // 1000
    i1 = rel_end * sample_rate // 1000
    i1 = min(i1, len(mono))
    if i0 >= len(mono):
        return []
    return list(mono[i0:i1])


def extract_amplitude_envelope(
    total_master_ms: int,
    segments: Sequence[EnvelopeSegment],
    *,
    gate_dbfs: float = NOISE_GATE_DBFS,
) -> list[float]:
    """Build the master ``amplitude_envelope`` aligned to voice segments."""
    frame_count = master_envelope_frame_count(total_master_ms)
    envelope = [0.0] * frame_count

    if not segments:
        if frame_count == 0:
            return envelope
        raise EnvelopeError("segments required when total_master_ms > 0")

    ordered = sorted(segments, key=lambda s: s.start_ms)
    if ordered[0].start_ms != 0:
        raise EnvelopeError("voice timeline must start at 0 ms")
    for previous, nxt in zip(ordered, ordered[1:]):
        if nxt.start_ms < previous.end_ms:
            raise EnvelopeError("voice segments must not overlap")
    if ordered[-1].end_ms > total_master_ms:
        raise EnvelopeError("segments must end at or before total_master_ms")

    prior_frame_stop = 0
    narration_audio: dict[str, tuple[list[float], int]] = {}

    for segment in ordered:
        frame_range = segment_frame_range(segment.start_ms, segment.end_ms)
        if frame_range.start < prior_frame_stop:
            raise EnvelopeError("segment frame ranges must not overlap")
        prior_frame_stop = frame_range.stop
        if segment.segment_kind in ("TWIST_PAD", "FOIA_AUDIO_SLOT"):
            pass  # envelope stays 0.0
        elif segment.segment_kind == "NARRATION":
            if not segment.audio_path:
                raise EnvelopeError("NARRATION requires audio_path")
            path = str(Path(segment.audio_path))
            if path not in narration_audio:
                narration_audio[path] = read_wav_mono_float(path)
            mono, sample_rate = narration_audio[path]
            expected_ms = segment.end_ms - segment.start_ms
            actual_ms = len(mono) * 1000 // sample_rate
            if abs(actual_ms - expected_ms) > 50:
                raise EnvelopeError(
                    f"WAV duration ~{actual_ms} ms does not match segment {expected_ms} ms"
                )
            for frame in frame_range:
                if frame >= frame_count:
                    raise EnvelopeError("segment frame exceeds master envelope length")
                t0 = frame_start_ms(frame)
                t1 = frame_start_ms(frame + 1) if frame + 1 < frame_count else total_master_ms
                window = _samples_for_master_window(
                    mono, sample_rate, segment.start_ms, t0, min(t1, segment.end_ms)
                )
                envelope[frame] = quantize_envelope_sample(rms_dbfs(window), gate_dbfs=gate_dbfs)
        else:
            raise EnvelopeError(f"unknown segment_kind {segment.segment_kind!r}")

    return envelope