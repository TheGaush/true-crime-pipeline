"""Procedural 48 kHz documentary cues.

Ten cues are synthesized from oscillators and noise. Nothing is read from a
sound library. A 20 Hz high-pass, short fades, and a -3 dBFS peak ceiling
run on every cue. Siren sweeps and ringing emergency tones are not generated.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.random import Generator, PCG64
from scipy.io import wavfile
from scipy.signal import butter, lfilter, sosfiltfilt

SAMPLE_RATE_HZ = 48_000
PEAK_DBFS = -3.0
PEAK_LINEAR = 10.0 ** (PEAK_DBFS / 20.0)
PCM_CEILING = 23_197
DC_LIMIT = 0.001
HIGHPASS_HZ = 20.0
FADE_MS = 5.0
ONSET_MS = 1.0

CUE_IDS = (
    "typewriter_key",
    "stamp_thud",
    "paper_slide",
    "bass_drop_hit",
    "tension_drone_pulse",
    "camera_shutter",
    "redaction_swipe",
    "map_pin_pop",
    "police_beep_clean",
    "subtle_whoosh",
)

DEFAULT_DURATION_MS = {
    "typewriter_key": 36,
    "stamp_thud": 180,
    "paper_slide": 420,
    "bass_drop_hit": 520,
    "tension_drone_pulse": 800,
    "camera_shutter": 90,
    "redaction_swipe": 280,
    "map_pin_pop": 110,
    "police_beep_clean": 150,
    "subtle_whoosh": 360,
}

PERCUSSIVE = frozenset({"typewriter_key", "stamp_thud", "camera_shutter", "map_pin_pop", "police_beep_clean"})

_ALIASES = {
    "gavel": "stamp_thud",
    "stamp": "stamp_thud",
    "conflict_stamp": "stamp_thud",
    "click": "typewriter_key",
    "typewriter": "typewriter_key",
    "typing_tap": "typewriter_key",
    "tick_sfx": "typewriter_key",
    "tape_click": "typewriter_key",
    "paper": "paper_slide",
    "highlighter_glide": "paper_slide",
    "bass": "bass_drop_hit",
    "drop": "bass_drop_hit",
    "drone": "tension_drone_pulse",
    "tension": "tension_drone_pulse",
    "shutter": "camera_shutter",
    "swipe": "redaction_swipe",
    "redaction": "redaction_swipe",
    "pin": "map_pin_pop",
    "pin_thud": "map_pin_pop",
    "pop": "map_pin_pop",
    "beep": "police_beep_clean",
    "whoosh": "subtle_whoosh",
}

_FORBIDDEN = frozenset({"siren", "siren_sweep", "911", "nine_one_one", "phone_ring", "emergency_ring", "patrol_wail"})
_LOG = logging.getLogger("python_motion.sfx")


class SfxSynthError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SfxRequest:
    cue_type: str
    duration_ms: int | None = None
    seed: int = 0
    intensity: float = 0.65
    channels: int = 1
    cache_dir: str | None = None


@dataclass(frozen=True)
class SfxCue:
    cue_type: str
    requested: str
    sample_rate_hz: int
    channels: int
    duration_ms: int
    pcm: np.ndarray
    wav_bytes: bytes
    sha256: str
    path: str | None
    cache_hit: bool
    peak_dbfs: float
    dc_offset: float
    warnings: tuple[dict[str, str], ...]


class SfxSynthesizer:
    """Synthesize one cue and cache the WAV by cue, seed, and duration."""

    def synthesize(self, request: SfxRequest) -> SfxCue:
        resolved, warnings = resolve_cue(request.cue_type)
        duration_ms = _duration(resolved, request.duration_ms, warnings)
        seed = _seed(request.seed)
        intensity = _intensity(request.intensity)
        channels = _channels(request.channels)
        cache_path = _cache_path(request.cache_dir, resolved, seed, duration_ms, intensity, channels)
        if cache_path is not None and cache_path.is_file():
            pcm = _read_pcm(cache_path, channels)
            wav_bytes = cache_path.read_bytes()
            return _finish(resolved, request.cue_type, duration_ms, channels, pcm, wav_bytes, cache_path, True, warnings)
        pcm = _render(resolved, duration_ms, seed, intensity, channels)
        wav_bytes = _wav_bytes(pcm)
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache_path.with_suffix(".tmp")
            tmp.write_bytes(wav_bytes)
            tmp.replace(cache_path)
        return _finish(resolved, request.cue_type, duration_ms, channels, pcm, wav_bytes, cache_path, False, warnings)


def resolve_cue(cue_type: str) -> tuple[str, list[dict[str, str]]]:
    name = cue_type.strip().lower().replace("-", "_").replace(" ", "_")
    warnings: list[dict[str, str]] = []
    if name in _FORBIDDEN:
        warnings.append({"code": "FORBIDDEN_TIMBRE", "from": name, "to": "paper_slide"})
        _warn(warnings[-1])
        return "paper_slide", warnings
    if name in CUE_IDS:
        return name, warnings
    alias = _ALIASES.get(name)
    if alias is not None:
        warnings.append({"code": "CUE_ALIAS", "from": name, "to": alias})
        _warn(warnings[-1])
        return alias, warnings
    warnings.append({"code": "UNKNOWN_CUE", "from": name or cue_type, "to": "paper_slide"})
    _warn(warnings[-1])
    return "paper_slide", warnings


def peak_dbfs(pcm: np.ndarray) -> float:
    peak = int(np.max(np.abs(pcm.astype(np.int32))))
    if peak <= 0:
        return -120.0
    return 20.0 * math.log10(peak / 32768.0)


def dc_offset(pcm: np.ndarray) -> float:
    return abs(float(np.mean(pcm.astype(np.float64))) / 32768.0)


def spectral_peak_hz(pcm: np.ndarray) -> float:
    mono = pcm.astype(np.float64)
    if mono.ndim == 2:
        mono = mono.mean(axis=1)
    window = np.hanning(mono.shape[0])
    spectrum = np.abs(np.fft.rfft(mono * window))
    if spectrum.shape[0] <= 1:
        return 0.0
    spectrum[0] = 0.0
    bin_index = int(np.argmax(spectrum))
    return bin_index * SAMPLE_RATE_HZ / mono.shape[0]


def _render(cue: str, duration_ms: int, seed: int, intensity: float, channels: int) -> np.ndarray:
    count = max(1, int(round(duration_ms * SAMPLE_RATE_HZ / 1000.0)))
    rng = Generator(PCG64(seed))
    raw = _CUE_FN[cue](count, rng, intensity)
    blocked = _highpass(raw)
    faded = _apply_fades(blocked, cue)
    centered = faded - float(np.mean(faded))
    mono = _quantize(centered)
    if channels == 1:
        return mono
    return np.column_stack((mono, mono))


def _typewriter(count: int, rng: Generator, intensity: float) -> np.ndarray:
    tick = _tone(count, 3200.0 + 400.0 * intensity, decay=18.0)
    click = _noise(count, rng) * _decay(count, 40.0)
    return tick * 0.65 + click * (0.35 + 0.25 * intensity)


def _stamp(count: int, rng: Generator, intensity: float) -> np.ndarray:
    body = _tone(count, 95.0, decay=8.0) + 0.35 * _tone(count, 190.0, decay=12.0)
    knock = _noise(count, rng) * _decay(count, 28.0)
    return body + knock * (0.25 + 0.2 * intensity)


def _paper(count: int, rng: Generator, intensity: float) -> np.ndarray:
    noise = _band_noise(count, rng, 700.0, 2800.0 + 800.0 * intensity)
    ramp = np.linspace(0.25, 1.0, count)
    return noise * ramp


def _bass(count: int, rng: Generator, intensity: float) -> np.ndarray:
    time = _time(count)
    start = 90.0
    end = 42.0
    span = float(time[-1]) if count > 1 else 1.0
    phase = 2.0 * math.pi * (start * time + (end - start) * time * time / (2.0 * span))
    fundamental = np.sin(phase) * _decay(count, 3.5)
    sub = np.sin(phase * 0.5) * (0.85 + 0.4 * intensity)
    grit = _noise(count, rng) * _decay(count, 16.0) * 0.08
    return fundamental + sub + grit


def _drone(count: int, rng: Generator, intensity: float) -> np.ndarray:
    time = _time(count)
    pulse = 0.62 + 0.38 * np.sin(2.0 * math.pi * 1.7 * time)
    low = np.sin(2.0 * math.pi * 98.0 * time)
    beat = np.sin(2.0 * math.pi * (104.0 + 2.0 * intensity) * time)
    air = _noise(count, rng) * 0.04
    return (low + 0.55 * beat) * pulse + air


def _shutter(count: int, rng: Generator, intensity: float) -> np.ndarray:
    first = _decay(count, 55.0)
    gap = int(min(count * 0.45, 0.03 * SAMPLE_RATE_HZ))
    second = np.zeros(count)
    if gap < count:
        second[gap:] = _decay(count - gap, 48.0)
    burst = _noise(count, rng) * (first + 0.7 * second)
    tick = _tone(count, 2400.0, decay=30.0) * (0.4 + 0.2 * intensity)
    return burst + tick


def _swipe(count: int, rng: Generator, intensity: float) -> np.ndarray:
    noise = _band_noise(count, rng, 500.0, 2200.0 + 600.0 * intensity)
    window = np.sin(np.linspace(0.0, math.pi, count)) ** 1.4
    return noise * window


def _pin(count: int, rng: Generator, intensity: float) -> np.ndarray:
    pop = _tone(count, 640.0 + 80.0 * intensity, decay=22.0)
    body = _tone(count, 180.0, decay=10.0) * 0.35
    tick = _noise(count, rng) * _decay(count, 50.0) * 0.2
    return pop + body + tick


def _beep(count: int, _rng: Generator, intensity: float) -> np.ndarray:
    return _tone(count, 1000.0, decay=0.0) * (0.75 + 0.25 * intensity)


def _whoosh(count: int, rng: Generator, intensity: float) -> np.ndarray:
    noise = _band_noise(count, rng, 300.0, 1800.0 + 900.0 * intensity)
    window = np.sin(np.linspace(0.0, math.pi, count)) ** 1.8
    return noise * window


_CUE_FN = {
    "typewriter_key": _typewriter,
    "stamp_thud": _stamp,
    "paper_slide": _paper,
    "bass_drop_hit": _bass,
    "tension_drone_pulse": _drone,
    "camera_shutter": _shutter,
    "redaction_swipe": _swipe,
    "map_pin_pop": _pin,
    "police_beep_clean": _beep,
    "subtle_whoosh": _whoosh,
}


def _tone(count: int, freq: float, decay: float) -> np.ndarray:
    wave = np.sin(2.0 * math.pi * freq * _time(count))
    if decay <= 0.0:
        return wave
    return wave * _decay(count, decay)


def _decay(count: int, rate: float) -> np.ndarray:
    return np.exp(-rate * _time(count))


def _noise(count: int, rng: Generator) -> np.ndarray:
    return rng.standard_normal(count)


def _band_noise(count: int, rng: Generator, low_hz: float, high_hz: float) -> np.ndarray:
    noise = _noise(count, rng)
    high = min(high_hz, SAMPLE_RATE_HZ * 0.45)
    low = min(low_hz, high * 0.5)
    sos = butter(2, [low, high], btype="bandpass", fs=SAMPLE_RATE_HZ, output="sos")
    try:
        return sosfiltfilt(sos, noise)
    except ValueError:
        return noise


def _time(count: int) -> np.ndarray:
    return np.arange(count, dtype=np.float64) / SAMPLE_RATE_HZ


def _highpass(samples: np.ndarray) -> np.ndarray:
    sos = butter(2, HIGHPASS_HZ, btype="highpass", fs=SAMPLE_RATE_HZ, output="sos")
    try:
        return sosfiltfilt(sos, samples)
    except ValueError:
        radius = math.exp(-2.0 * math.pi * HIGHPASS_HZ / SAMPLE_RATE_HZ)
        return lfilter([1.0, -1.0], [1.0, -radius], samples)


def _apply_fades(samples: np.ndarray, cue: str) -> np.ndarray:
    count = samples.shape[0]
    fade_cap = max(1, count // 4)
    fade_out = min(int(FADE_MS * SAMPLE_RATE_HZ / 1000.0), fade_cap)
    if cue in PERCUSSIVE:
        fade_in = min(int(ONSET_MS * SAMPLE_RATE_HZ / 1000.0), fade_cap)
    else:
        fade_in = min(int(FADE_MS * SAMPLE_RATE_HZ / 1000.0), fade_cap)
    envelope = np.ones(count, dtype=np.float64)
    if fade_in > 1:
        envelope[:fade_in] = np.linspace(0.0, 1.0, fade_in, endpoint=False)
    if fade_out > 1:
        envelope[-fade_out:] *= np.linspace(1.0, 0.0, fade_out, endpoint=True)
    return samples * envelope


def _quantize(samples: np.ndarray) -> np.ndarray:
    if not np.all(np.isfinite(samples)):
        raise SfxSynthError("NON_FINITE", "synthesis produced a non-finite sample")
    peak = float(np.max(np.abs(samples)))
    scaled = samples * (PEAK_LINEAR / peak) if peak > 0.0 else samples
    codes = np.rint(scaled * 32767.0)
    return np.clip(codes, -PCM_CEILING, PCM_CEILING).astype(np.int16)


def _wav_bytes(pcm: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    wavfile.write(buffer, SAMPLE_RATE_HZ, pcm)
    return buffer.getvalue()


def _read_pcm(path: Path, channels: int) -> np.ndarray:
    rate, data = wavfile.read(path)
    if rate != SAMPLE_RATE_HZ or data.dtype != np.int16:
        raise SfxSynthError("CACHE", f"cached wav at {path} is not 48 kHz pcm_s16le")
    if channels == 1 and data.ndim != 1:
        raise SfxSynthError("CACHE", f"cached wav at {path} is not mono")
    if channels == 2 and (data.ndim != 2 or data.shape[1] != 2):
        raise SfxSynthError("CACHE", f"cached wav at {path} is not stereo")
    return data


def _finish(
    cue: str,
    requested: str,
    duration_ms: int,
    channels: int,
    pcm: np.ndarray,
    wav_bytes: bytes,
    path: Path | None,
    cache_hit: bool,
    warnings: list[dict[str, str]],
) -> SfxCue:
    if not np.all(np.isfinite(pcm)):
        raise SfxSynthError("NON_FINITE", "pcm contains a non-finite sample")
    return SfxCue(
        cue_type=cue,
        requested=requested,
        sample_rate_hz=SAMPLE_RATE_HZ,
        channels=channels,
        duration_ms=duration_ms,
        pcm=pcm,
        wav_bytes=wav_bytes,
        sha256=hashlib.sha256(wav_bytes).hexdigest(),
        path=None if path is None else str(path),
        cache_hit=cache_hit,
        peak_dbfs=peak_dbfs(pcm),
        dc_offset=dc_offset(pcm),
        warnings=tuple(warnings),
    )


def _duration(cue: str, requested: int | None, warnings: list[dict[str, str]]) -> int:
    duration = DEFAULT_DURATION_MS[cue] if requested is None else requested
    if isinstance(duration, bool) or not isinstance(duration, int):
        raise SfxSynthError("DURATION", "duration_ms must be an integer")
    if duration < 10:
        warnings.append({"code": "DURATION_CLAMP", "from": str(duration), "to": "10"})
        _warn(warnings[-1])
        return 10
    if duration > 8_000:
        warnings.append({"code": "DURATION_CLAMP", "from": str(duration), "to": "8000"})
        _warn(warnings[-1])
        return 8_000
    return duration


def _seed(seed: int) -> int:
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise SfxSynthError("SEED", "seed must be a non-negative integer")
    return seed


def _intensity(intensity: float) -> float:
    if isinstance(intensity, bool) or not isinstance(intensity, (int, float)) or not math.isfinite(float(intensity)):
        raise SfxSynthError("INTENSITY", "intensity must be a finite number from 0 to 1")
    value = float(intensity)
    if value < 0.0 or value > 1.0:
        raise SfxSynthError("INTENSITY", "intensity must be a finite number from 0 to 1")
    return value


def _channels(channels: int) -> int:
    if channels not in {1, 2}:
        raise SfxSynthError("CHANNELS", "channels must be 1 or 2")
    return channels


def _cache_path(
    cache_dir: str | None,
    cue: str,
    seed: int,
    duration_ms: int,
    intensity: float,
    channels: int,
) -> Path | None:
    if cache_dir is None:
        return None
    intensity_code = int(round(intensity * 1000.0))
    name = f"{cue}__s{seed}__d{duration_ms}__i{intensity_code}__c{channels}.wav"
    return Path(cache_dir) / name


def _warn(payload: dict[str, str]) -> None:
    _LOG.warning(json.dumps(payload, sort_keys=True))
