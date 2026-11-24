"""Config-driven Gemini TTS adapter with per-chunk loudness and EQ consistency.

Pure-Python 24 kHz → 48 kHz resampling, stereo expansion, spectral tilt matching,
and integrated loudness normalization to -16.0 LUFS. No FFmpeg or network.
"""

from __future__ import annotations

import io
import math
import re
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

GEMINI_RAW_SAMPLE_RATE_HZ = 24_000
OUTPUT_SAMPLE_RATE_HZ = 48_000
OUTPUT_CHANNELS = 2
TARGET_LUFS = -16.0
LUFS_TOLERANCE_LU = 0.5
REFERENCE_TILT_DB = -4.0

DIRECTING_STYLE_PREFIX = (
    "[Documentary true-crime narrator: calm, authoritative, measured pacing] "
)


class GeminiTtsClient(Protocol):
    """Injectable offline TTS transport returning mono s16le PCM."""

    def synthesize(self, *, model_id: str, text: str, sample_rate_hz: int) -> bytes: ...


@dataclass(frozen=True, slots=True)
class GeminiTtsConfig:
    """TTS model registry slice loaded from providers.yaml."""

    provider_id: str
    primary_model_id: str
    alternate_model_id: str


@dataclass(frozen=True, slots=True)
class NormalizedChunk:
    """One mastered narration chunk ready for timeline assembly."""

    pcm_s16le: bytes
    sample_rate_hz: int
    channels: int
    integrated_lufs: float
    model_id: str
    style_prefixed_text: str


def default_providers_path() -> Path:
    """Locate repo-root providers.yaml from this module or the cwd."""
    candidates: list[Path] = []
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "providers.yaml")
    cwd = Path.cwd()
    for parent in (cwd, *cwd.parents):
        candidates.append(parent / "providers.yaml")
    for path in candidates:
        if path.is_file():
            return path
    raise FileNotFoundError("providers.yaml not found")


def load_gemini_tts_config(path: str | Path | None = None) -> GeminiTtsConfig:
    """Load Gemini TTS model IDs from providers.yaml without copying them into source."""
    registry = Path(path) if path is not None else default_providers_path()
    lines = registry.read_text(encoding="utf-8").splitlines()
    in_providers = False
    in_tts = False
    models: dict[str, str] = {}
    provider_id = "tts"

    for line in lines:
        if line.strip() == "providers:" and not line[:1].isspace():
            in_providers = True
            continue
        if in_providers and line and not line[0].isspace():
            break
        if in_providers and line.startswith("  tts:"):
            in_tts = True
            continue
        if in_tts and line.startswith("  ") and not line.startswith("    ") and line.strip():
            if not line.strip().startswith("-"):
                in_tts = False
                continue
        if not in_tts:
            continue
        if m := re.match(r"\s*provider_id:\s*(\S+)", line):
            provider_id = m.group(1)
            continue
        if m := re.match(r"\s*-\s*id:\s*(\S+)", line):
            current_id = m.group(1)
            models[current_id] = ""
            continue
        if m := re.match(r"\s*role:\s*(\S+)", line):
            if models:
                last_key = next(reversed(models))
                models[last_key] = m.group(1)

    primary = next((k for k, role in models.items() if role == "primary_narration"), "")
    alternate = next((k for k, role in models.items() if role == "alternate"), "")
    secondary_ids = [k for k in models if k not in {primary, alternate}]
    if not primary and models:
        primary = next(iter(models))
    if not alternate and secondary_ids:
        alternate = secondary_ids[0]
    elif not alternate and len(models) > 1:
        alternate = list(models.keys())[1]

    if not primary:
        raise ValueError(f"No TTS models found in {registry}")

    return GeminiTtsConfig(
        provider_id=provider_id,
        primary_model_id=primary,
        alternate_model_id=alternate or primary,
    )


def _s16_bytes_to_floats(pcm: bytes) -> list[float]:
    count = len(pcm) // 2
    samples = struct.unpack(f"<{count}h", pcm)
    return [s / 32768.0 for s in samples]


def _floats_to_s16_bytes(samples: list[float]) -> bytes:
    clipped = [max(-1.0, min(1.0, s)) for s in samples]
    ints = [int(round(s * 32767.0)) for s in clipped]
    return struct.pack(f"<{len(ints)}h", *ints)


def _resample_linear_mono(samples: list[float], src_hz: int, dst_hz: int) -> list[float]:
    if src_hz == dst_hz:
        return list(samples)
    if not samples:
        return []
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


def _mono_to_stereo_interleaved(samples: list[float]) -> list[float]:
    stereo: list[float] = []
    for sample in samples:
        stereo.extend((sample, sample))
    return stereo


def _stereo_to_mono(samples: list[float]) -> list[float]:
    if len(samples) < 2:
        return samples
    mono: list[float] = []
    for i in range(0, len(samples) - 1, 2):
        mono.append(0.5 * (samples[i] + samples[i + 1]))
    return mono


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
    """BS.1770 K-weighting biquad cascade at 48 kHz (stereo downstream)."""
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
        left = floats[0::2]
        right = floats[1::2]
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


def _normalize_lufs(stereo: list[float], sample_rate_hz: int, channels: int) -> tuple[list[float], float]:
    _ = sample_rate_hz
    working = list(stereo)
    for _ in range(3):
        loudness = _measure_lufs_floats(working, channels)
        if not math.isfinite(loudness):
            return working, loudness
        gain = 10.0 ** ((TARGET_LUFS - loudness) / 20.0)
        working = [s * gain for s in working]
        working = _limit_peak(working)
    final_lufs = _measure_lufs_floats(working, channels)
    return working, final_lufs


def process_raw_gemini_pcm(raw_pcm: bytes, *, source_rate_hz: int = GEMINI_RAW_SAMPLE_RATE_HZ) -> NormalizedChunk:
    """Resample, stereo-expand, EQ-match, and loudness-normalize one Gemini PCM blob."""
    mono = _s16_bytes_to_floats(raw_pcm)
    at_48 = _resample_linear_mono(mono, source_rate_hz, OUTPUT_SAMPLE_RATE_HZ)
    at_48 = _apply_tilt_match(at_48, OUTPUT_SAMPLE_RATE_HZ)
    stereo = _mono_to_stereo_interleaved(at_48)
    stereo, lufs = _normalize_lufs(stereo, OUTPUT_SAMPLE_RATE_HZ, OUTPUT_CHANNELS)
    return NormalizedChunk(
        pcm_s16le=_floats_to_s16_bytes(stereo),
        sample_rate_hz=OUTPUT_SAMPLE_RATE_HZ,
        channels=OUTPUT_CHANNELS,
        integrated_lufs=lufs,
        model_id="",
        style_prefixed_text="",
    )


@dataclass(slots=True)
class GeminiTtsAdapter:
    """Offline Gemini narration adapter with per-chunk mastering parity."""

    client: GeminiTtsClient
    config: GeminiTtsConfig
    style_prefix: str = DIRECTING_STYLE_PREFIX
    use_alternate_model: bool = False

    @classmethod
    def from_providers(
        cls,
        client: GeminiTtsClient,
        *,
        providers_path: str | Path | None = None,
        style_prefix: str = DIRECTING_STYLE_PREFIX,
        use_alternate_model: bool = False,
    ) -> GeminiTtsAdapter:
        config = load_gemini_tts_config(providers_path)
        return cls(
            client=client,
            config=config,
            style_prefix=style_prefix,
            use_alternate_model=use_alternate_model,
        )

    @property
    def model_id(self) -> str:
        if self.use_alternate_model:
            return self.config.alternate_model_id
        return self.config.primary_model_id

    def synthesize_chunk(self, narration_text: str) -> NormalizedChunk:
        """Synthesize one chunk with the shared style prefix and mastering pipeline."""
        styled = f"{self.style_prefix}{narration_text}"
        raw = self.client.synthesize(
            model_id=self.model_id,
            text=styled,
            sample_rate_hz=GEMINI_RAW_SAMPLE_RATE_HZ,
        )
        mastered = process_raw_gemini_pcm(raw)
        return NormalizedChunk(
            pcm_s16le=mastered.pcm_s16le,
            sample_rate_hz=mastered.sample_rate_hz,
            channels=mastered.channels,
            integrated_lufs=mastered.integrated_lufs,
            model_id=self.model_id,
            style_prefixed_text=styled,
        )

    def synthesize_chunks(self, narration_texts: list[str]) -> list[NormalizedChunk]:
        return [self.synthesize_chunk(text) for text in narration_texts]


def pcm_to_wav_bytes(
    pcm_s16le: bytes,
    *,
    sample_rate_hz: int,
    channels: int,
) -> bytes:
    """Wrap interleaved s16le PCM in a WAV container (stdlib wave module)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate_hz)
        wf.writeframes(pcm_s16le)
    return buf.getvalue()


def wav_bytes_to_pcm(wav_bytes: bytes) -> tuple[bytes, int, int]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, rate, channels