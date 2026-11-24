"""Config-driven DeepSeek Speech TTS failover adapter.

Reads model IDs and planning character rates from ``providers.yaml``, accepts an
injected HTTP client (no live sockets in-module), normalizes each chunk to 48 kHz
stereo PCM at -16.0 LUFS, and enforces a single active ``voice_id`` per episode.
Mid-episode primary failures engage the registry failover model and re-synthesize
earlier chunks on the failover voice so timbre never drifts.
"""

from __future__ import annotations

import io
import math
import re
import struct
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

PLANNING_NARRATION_CHARS_PER_EPISODE = 12_000
TTS_SHARE_OF_EPISODE_BUNDLE = 0.5
DEEPSEEK_RAW_SAMPLE_RATE_HZ = 24_000
OUTPUT_SAMPLE_RATE_HZ = 48_000
OUTPUT_CHANNELS = 2
TARGET_LUFS = -16.0
LUFS_TOLERANCE_LU = 0.5
REFERENCE_TILT_DB = -4.0
SPEECH_API_PATH = "/v1/audio/speech"

DIRECTING_STYLE_PREFIX = (
    "[Documentary true-crime narrator: calm, authoritative, measured pacing] "
)


class DeepSeekTtsPrimaryError(RuntimeError):
    """Primary DeepSeek speech synthesis failed; caller may engage failover."""


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status_code: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)


class DeepSeekHttpClient(Protocol):
    """Injectable HTTP transport; production wiring lives outside this package."""

    def post(self, *, path: str, json_body: dict[str, Any]) -> HttpResponse: ...


@dataclass(frozen=True, slots=True)
class DeepSeekTtsConfig:
    """DeepSeek speech + TTS registry slice loaded from providers.yaml."""

    billing_provider_id: str
    speech_model_id: str
    failover_model_id: str
    conservative_micro_usd_per_char: int


@dataclass(frozen=True, slots=True)
class NormalizedChunk:
    pcm_s16le: bytes
    sample_rate_hz: int
    channels: int
    integrated_lufs: float
    model_id: str
    voice_id: str
    style_prefixed_text: str


@dataclass(slots=True)
class ChunkSynthesisRecord:
    chunk_index: int
    narration_text: str
    voice_id: str
    model_id: str
    needs_resynthesis: bool = False
    audio: NormalizedChunk | None = None


@dataclass(slots=True)
class EpisodeSynthesisResult:
    episode_id: str
    voice_id: str
    failover_model_id: str
    chunks: list[ChunkSynthesisRecord]
    engaged_failover: bool


def default_providers_path() -> Path:
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


def _parse_tts_models(registry_text: str) -> dict[str, str]:
    in_providers = False
    in_tts = False
    models: dict[str, str] = {}
    current_id: str | None = None

    for line in registry_text.splitlines():
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
        if m := re.match(r"\s*-\s*id:\s*(\S+)", line):
            current_id = m.group(1)
            models[current_id] = ""
            continue
        if m := re.match(r"\s*role:\s*(\S+)", line):
            if current_id is not None:
                models[current_id] = m.group(1)
    return models


def _first_deepseek_speech_model(registry_text: str) -> str:
    in_providers = False
    in_deepseek = False
    for line in registry_text.splitlines():
        if line.strip() == "providers:" and not line[:1].isspace():
            in_providers = True
            continue
        if in_providers and line and not line[0].isspace():
            break
        if in_providers and line.startswith("  deepseek_chat:"):
            in_deepseek = True
            continue
        if in_deepseek and line.startswith("  ") and not line.startswith("    ") and line.strip():
            if not line.strip().startswith("-"):
                break
        if not in_deepseek:
            continue
        if m := re.match(r"\s*-\s*id:\s*(\S+)", line):
            return m.group(1)
    raise ValueError("No deepseek_chat model ids found in providers.yaml")


def _read_micro_usd_per_usd(registry_text: str) -> int:
    for line in registry_text.splitlines():
        if m := re.match(r"^micro_usd_per_usd:\s*(\d+)", line):
            return int(m.group(1))
    return 1_000_000


def _read_tts_episode_conservative_usd(registry_text: str) -> float:
    in_tts = False
    for line in registry_text.splitlines():
        if line.startswith("  tts:"):
            in_tts = True
            continue
        if in_tts and line.startswith("  ") and not line.startswith("    ") and line.strip():
            if not line.strip().startswith("usd_"):
                break
        if not in_tts:
            continue
        if m := re.match(
            r"\s*usd_per_episode_with_vision_qa_conservative:\s*([0-9.]+)",
            line,
        ):
            return float(m.group(1))
    raise ValueError("tts.usd_per_episode_with_vision_qa_conservative missing from providers.yaml")


def load_deepseek_tts_config(path: str | Path | None = None) -> DeepSeekTtsConfig:
    """Load DeepSeek speech model, failover model id, and planning character rates."""
    registry = Path(path) if path is not None else default_providers_path()
    text = registry.read_text(encoding="utf-8")
    models = _parse_tts_models(text)
    failover_model_id = next(
        (model_id for model_id, role in models.items() if role == "alternate"),
        "",
    )
    if not failover_model_id:
        raise ValueError(f"No alternate (failover) TTS model in {registry}")
    speech_model_id = _first_deepseek_speech_model(text)
    micro_scale = _read_micro_usd_per_usd(text)
    bundle_usd = _read_tts_episode_conservative_usd(text)
    tts_plan_usd = bundle_usd * TTS_SHARE_OF_EPISODE_BUNDLE
    conservative_micro_usd_per_char = max(
        1,
        int(
            tts_plan_usd
            * micro_scale
            / PLANNING_NARRATION_CHARS_PER_EPISODE
        ),
    )
    return DeepSeekTtsConfig(
        billing_provider_id="deepseek_chat",
        speech_model_id=speech_model_id,
        failover_model_id=failover_model_id,
        conservative_micro_usd_per_char=conservative_micro_usd_per_char,
    )


def estimate_chunk_micro_usd(config: DeepSeekTtsConfig, char_count: int) -> int:
    return config.conservative_micro_usd_per_char * char_count


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


def measure_integrated_lufs(pcm_s16le: bytes, sample_rate_hz: int, channels: int) -> float:
    floats = _s16_bytes_to_floats(pcm_s16le)
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


def _normalize_lufs(stereo: list[float], sample_rate_hz: int, channels: int) -> tuple[list[float], float]:
    pcm = _floats_to_s16_bytes(stereo)
    loudness = measure_integrated_lufs(pcm, sample_rate_hz, channels)
    if not math.isfinite(loudness):
        return stereo, loudness
    gain_db = TARGET_LUFS - loudness
    gain = 10.0 ** (gain_db / 20.0)
    scaled = [s * gain for s in stereo]
    pcm2 = _floats_to_s16_bytes(scaled)
    final_lufs = measure_integrated_lufs(pcm2, sample_rate_hz, channels)
    return scaled, final_lufs


def process_raw_deepseek_pcm(
    raw_pcm: bytes,
    *,
    source_rate_hz: int = DEEPSEEK_RAW_SAMPLE_RATE_HZ,
    model_id: str = "",
    voice_id: str = "",
    style_prefixed_text: str = "",
) -> NormalizedChunk:
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
        model_id=model_id,
        voice_id=voice_id,
        style_prefixed_text=style_prefixed_text,
    )


def pcm_to_wav_bytes(pcm_s16le: bytes, *, sample_rate_hz: int, channels: int) -> bytes:
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


@dataclass(slots=True)
class EpisodeVoiceSession:
    episode_id: str
    voice_id: str
    model_id: str
    failover_voice_id: str
    failover_model_id: str
    failover_engaged: bool = False

    def engage_failover(self) -> None:
        self.failover_engaged = True
        self.voice_id = self.failover_voice_id
        self.model_id = self.failover_model_id


@dataclass(slots=True)
class DeepSeekTtsAdapter:
    http: DeepSeekHttpClient
    config: DeepSeekTtsConfig
    style_prefix: str = DIRECTING_STYLE_PREFIX

    @classmethod
    def from_providers(
        cls,
        http: DeepSeekHttpClient,
        *,
        providers_path: str | Path | None = None,
        style_prefix: str = DIRECTING_STYLE_PREFIX,
    ) -> DeepSeekTtsAdapter:
        config = load_deepseek_tts_config(providers_path)
        return cls(http=http, config=config, style_prefix=style_prefix)

    def primary_voice_id(self, episode_id: str) -> str:
        return f"{episode_id}:deepseek-speech"

    def failover_voice_id(self, episode_id: str) -> str:
        return f"{episode_id}:failover:{self.config.failover_model_id}"

    def new_session(self, episode_id: str) -> EpisodeVoiceSession:
        return EpisodeVoiceSession(
            episode_id=episode_id,
            voice_id=self.primary_voice_id(episode_id),
            model_id=self.config.speech_model_id,
            failover_voice_id=self.failover_voice_id(episode_id),
            failover_model_id=self.config.failover_model_id,
        )

    def _styled_text(self, narration_text: str) -> str:
        return f"{self.style_prefix}{narration_text}"

    def _request_pcm(self, *, model_id: str, voice_id: str, text: str) -> bytes:
        payload = {
            "model": model_id,
            "voice": voice_id,
            "input": text,
            "response_format": "pcm",
            "sample_rate": DEEPSEEK_RAW_SAMPLE_RATE_HZ,
        }
        response = self.http.post(path=SPEECH_API_PATH, json_body=payload)
        if response.status_code in {429, 500, 502, 503, 504}:
            raise DeepSeekTtsPrimaryError(
                f"DeepSeek speech synthesis unavailable ({response.status_code})"
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"DeepSeek speech synthesis failed ({response.status_code})"
            )
        if not response.body:
            raise RuntimeError("DeepSeek speech synthesis returned empty audio")
        return response.body

    def synthesize_chunk(
        self,
        session: EpisodeVoiceSession,
        chunk_index: int,
        narration_text: str,
    ) -> ChunkSynthesisRecord:
        styled = self._styled_text(narration_text)
        raw = self._request_pcm(
            model_id=session.model_id,
            voice_id=session.voice_id,
            text=styled,
        )
        mastered = process_raw_deepseek_pcm(
            raw,
            model_id=session.model_id,
            voice_id=session.voice_id,
            style_prefixed_text=styled,
        )
        return ChunkSynthesisRecord(
            chunk_index=chunk_index,
            narration_text=narration_text,
            voice_id=session.voice_id,
            model_id=session.model_id,
            needs_resynthesis=False,
            audio=mastered,
        )

    def synthesize_episode(
        self,
        episode_id: str,
        narration_texts: list[str],
    ) -> EpisodeSynthesisResult:
        session = self.new_session(episode_id)
        records: list[ChunkSynthesisRecord] = []

        for idx, text in enumerate(narration_texts):
            try:
                record = self.synthesize_chunk(session, idx, text)
            except DeepSeekTtsPrimaryError:
                if session.failover_engaged:
                    raise
                session.engage_failover()
                for prior in records:
                    prior.needs_resynthesis = True
                record = self.synthesize_chunk(session, idx, text)
            records.append(record)

        for record in records:
            if record.needs_resynthesis:
                refreshed = self.synthesize_chunk(session, record.chunk_index, record.narration_text)
                record.voice_id = refreshed.voice_id
                record.model_id = refreshed.model_id
                record.audio = refreshed.audio
                record.needs_resynthesis = False

        return EpisodeSynthesisResult(
            episode_id=episode_id,
            voice_id=session.voice_id,
            failover_model_id=self.config.failover_model_id,
            chunks=records,
            engaged_failover=session.failover_engaged,
        )