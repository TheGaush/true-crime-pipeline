"""Optional Google Vids manual-export voiceover adapter (google-vids-tts-adapter@1).

Formats bracket-tag directing scripts for Google Vids voiceover, and — only when the
caller explicitly selects this fallback — extracts audio from a user-exported container
via an injected stream reader (tests supply PCM directly; production may wire FFmpeg).

Output invariant: 48 kHz stereo s16le PCM at -16.0 LUFS (+/- 0.5 LU). Pure stdlib.
"""

from __future__ import annotations

import math
import re
import struct
from dataclasses import dataclass
from typing import Protocol

OUTPUT_SAMPLE_RATE_HZ = 48_000
OUTPUT_CHANNELS = 2
TARGET_LUFS = -16.0
LUFS_TOLERANCE_LU = 0.5
REFERENCE_TILT_DB = -4.0

BRACKET_TAG_PATTERN = re.compile(r"\[(?P<tag>[a-zA-Z][\w-]*)\]\s*")
GOOGLE_VIDS_PROVIDER_ID = "google-vids-manual-export"


class MissingAudioStreamError(Exception):
    """Raised when a Google Vids export container has no readable audio stream."""


class GoogleVidsNotSelectedError(Exception):
    """Raised when audio extraction is attempted without an explicit Google Vids selection."""


class AudioStreamReader(Protocol):
    """Injectable export demuxer — returns interleaved s16le PCM or None if silent/video-only."""

    def read_pcm(self, export_bytes: bytes) -> bytes | None: ...


@dataclass(frozen=True, slots=True)
class GoogleVidsSelection:
    """Explicit opt-in to the Google Vids manual-export fallback."""

    explicit: bool
    provider_id: str = GOOGLE_VIDS_PROVIDER_ID

    def require_explicit(self) -> None:
        if not self.explicit:
            raise GoogleVidsNotSelectedError(
                "Google Vids audio extraction requires explicit selection (explicit=True)"
            )


@dataclass(frozen=True, slots=True)
class ExtractedVoiceover:
    """Mastered voiceover extracted from a Google Vids export."""

    pcm_s16le: bytes
    sample_rate_hz: int
    channels: int
    integrated_lufs: float
    formatted_script: str
    provider_id: str


def format_bracket_tag_script(raw_script: str) -> str:
    """Turn inline ``[calmly]`` / ``[dramatically]`` markers into Google Vids script blocks."""
    text = raw_script.strip()
    if not text:
        return ""

    blocks: list[str] = []
    tag = "neutral"
    cursor = 0

    for match in BRACKET_TAG_PATTERN.finditer(text):
        before = text[cursor : match.start()].strip()
        if before:
            blocks.append(f"[Direction: {tag}]\n{before}")
        tag = match.group("tag").lower()
        cursor = match.end()

    tail = text[cursor:].strip()
    if tail:
        blocks.append(f"[Direction: {tag}]\n{tail}")

    return "\n\n".join(blocks)


def _s16_bytes_to_floats(pcm: bytes) -> list[float]:
    count = len(pcm) // 2
    if count == 0:
        return []
    samples = struct.unpack(f"<{count}h", pcm)
    return [s / 32768.0 for s in samples]


def _floats_to_s16_bytes(samples: list[float]) -> bytes:
    clipped = [max(-1.0, min(1.0, s)) for s in samples]
    ints = [int(round(s * 32767.0)) for s in clipped]
    return struct.pack(f"<{len(ints)}h", *ints)


def _deinterleave_stereo(stereo: list[float]) -> tuple[list[float], list[float]]:
    left = stereo[0::2]
    right = stereo[1::2]
    min_len = min(len(left), len(right))
    return left[:min_len], right[:min_len]


def _interleave_stereo(left: list[float], right: list[float]) -> list[float]:
    out: list[float] = []
    for idx in range(min(len(left), len(right))):
        out.extend((left[idx], right[idx]))
    return out


def _ensure_stereo_interleaved(floats: list[float], channels: int) -> list[float]:
    if channels == 2:
        return floats
    return _interleave_stereo(floats, floats)


def _resample_linear(samples: list[float], src_hz: int, dst_hz: int) -> list[float]:
    if src_hz == dst_hz or not samples:
        return list(samples)
    ratio = dst_hz / src_hz
    out_len = max(1, int(math.floor(len(samples) * ratio)))
    out: list[float] = []
    for i in range(out_len):
        src_pos = i / ratio
        left = int(math.floor(src_pos))
        right = min(left + 1, len(samples) - 1)
        frac = src_pos - left
        out.append(samples[left] * (1.0 - frac) + samples[right] * frac)
    return out


def _stereo_resample(stereo: list[float], src_hz: int, dst_hz: int) -> list[float]:
    left, right = _deinterleave_stereo(stereo)
    left_r = _resample_linear(left, src_hz, dst_hz)
    right_r = _resample_linear(right, src_hz, dst_hz)
    return _interleave_stereo(left_r, right_r)


def _one_pole_lowpass(samples: list[float], cutoff_hz: float, sample_rate_hz: int) -> list[float]:
    if not samples:
        return []
    dt = 1.0 / sample_rate_hz
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    alpha = dt / (rc + dt)
    out = [samples[0]]
    for i in range(1, len(samples)):
        out.append(out[-1] + alpha * (samples[i] - out[-1]))
    return out


def _measure_tilt_db(mono: list[float], sample_rate_hz: int) -> float:
    if not mono:
        return REFERENCE_TILT_DB
    low = _one_pole_lowpass(mono, 900.0, sample_rate_hz)
    high = [a - b for a, b in zip(mono, low, strict=True)]
    lf = math.sqrt(sum(x * x for x in low) / len(low))
    hf = math.sqrt(sum(x * x for x in high) / len(high))
    if lf <= 1e-12:
        return REFERENCE_TILT_DB
    return 20.0 * math.log10(max(hf, 1e-12) / lf)


def _apply_tilt_match(mono: list[float], sample_rate_hz: int) -> list[float]:
    measured = _measure_tilt_db(mono, sample_rate_hz)
    correction_db = REFERENCE_TILT_DB - measured
    gain = 10.0 ** (correction_db / 20.0)
    low = _one_pole_lowpass(mono, 900.0, sample_rate_hz)
    high = [a - b for a, b in zip(mono, low, strict=True)]
    boosted_high = [h * gain for h in high]
    return [lo + hi for lo, hi in zip(low, boosted_high, strict=True)]


def _biquad_apply(samples: list[float], b0: float, b1: float, b2: float, a1: float, a2: float) -> list[float]:
    if not samples:
        return []
    x1 = x2 = y1 = y2 = 0.0
    out: list[float] = []
    for x0 in samples:
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        out.append(y0)
        x2, x1 = x1, x0
        y2, y1 = y1, y0
    return out


def _k_weight_channel(samples: list[float]) -> list[float]:
    stage1 = _biquad_apply(
        samples,
        1.53512485958697,
        -2.69169618940624,
        1.19841372421279,
        -1.69065929318241,
        0.73248077421585,
    )
    return _biquad_apply(stage1, 1.0, -2.0, 1.0, -1.99004745483398, 0.99007225036621)


def _measure_lufs_floats(floats: list[float], channels: int) -> float:
    if channels == 2:
        left, right = _deinterleave_stereo(floats)
    else:
        left = right = floats
    weighted = _k_weight_channel(left) + _k_weight_channel(right)
    if not weighted:
        return float("-inf")
    mean_square = sum(x * x for x in weighted) / len(weighted)
    if mean_square <= 0.0:
        return float("-inf")
    return -0.691 + 10.0 * math.log10(mean_square)


def measure_integrated_lufs(pcm_s16le: bytes, sample_rate_hz: int, channels: int) -> float:
    """Measure integrated loudness (LUFS) for interleaved s16le PCM."""
    _ = sample_rate_hz
    floats = _s16_bytes_to_floats(pcm_s16le)
    return _measure_lufs_floats(floats, channels)


def _limit_peak(stereo: list[float], ceiling: float = 0.98) -> list[float]:
    peak = max((abs(s) for s in stereo), default=0.0)
    if peak <= ceiling or peak == 0.0:
        return stereo
    scale = ceiling / peak
    return [s * scale for s in stereo]


def _normalize_lufs(stereo: list[float], channels: int) -> tuple[list[float], float]:
    working = list(stereo)
    for _ in range(3):
        loudness = _measure_lufs_floats(working, channels)
        if not math.isfinite(loudness):
            return working, loudness
        gain = 10.0 ** ((TARGET_LUFS - loudness) / 20.0)
        working = [s * gain for s in working]
        working = _limit_peak(working)
    return working, _measure_lufs_floats(working, channels)


def normalize_export_pcm(
    raw_pcm: bytes,
    *,
    source_sample_rate_hz: int,
    source_channels: int = 1,
) -> tuple[bytes, float]:
    """Resample to 48 kHz stereo, mild EQ parity, and -16 LUFS mastering."""
    floats = _s16_bytes_to_floats(raw_pcm)
    stereo = _ensure_stereo_interleaved(floats, source_channels)
    ch = 2 if source_channels >= 2 else 1
    if ch == 1 and source_channels == 1:
        stereo = _interleave_stereo(floats, floats)

    if source_sample_rate_hz != OUTPUT_SAMPLE_RATE_HZ:
        stereo = _stereo_resample(stereo, source_sample_rate_hz, OUTPUT_SAMPLE_RATE_HZ)

    left, right = _deinterleave_stereo(stereo)
    mono_blend = [(l + r) * 0.5 for l, r in zip(left, right, strict=True)]
    matched = _apply_tilt_match(mono_blend, OUTPUT_SAMPLE_RATE_HZ)
    stereo = _interleave_stereo(matched, matched)
    stereo, lufs = _normalize_lufs(stereo, OUTPUT_CHANNELS)
    return _floats_to_s16_bytes(stereo), lufs


@dataclass(slots=True)
class GoogleVidsTtsAdapter:
    """Optional manual Google Vids export fallback."""

    def format_script(self, raw_script: str) -> str:
        return format_bracket_tag_script(raw_script)

    def extract_voiceover(
        self,
        *,
        selection: GoogleVidsSelection,
        export_bytes: bytes,
        audio_stream: AudioStreamReader,
        formatted_script: str,
        source_sample_rate_hz: int = OUTPUT_SAMPLE_RATE_HZ,
        source_channels: int = 2,
    ) -> ExtractedVoiceover:
        """Extract and master audio only with explicit selection and an injected stream."""
        selection.require_explicit()
        raw_pcm = audio_stream.read_pcm(export_bytes)
        if raw_pcm is None:
            raise MissingAudioStreamError("Google Vids export has no audio stream")
        pcm, lufs = normalize_export_pcm(
            raw_pcm,
            source_sample_rate_hz=source_sample_rate_hz,
            source_channels=source_channels,
        )
        return ExtractedVoiceover(
            pcm_s16le=pcm,
            sample_rate_hz=OUTPUT_SAMPLE_RATE_HZ,
            channels=OUTPUT_CHANNELS,
            integrated_lufs=lufs,
            formatted_script=formatted_script,
            provider_id=selection.provider_id,
        )