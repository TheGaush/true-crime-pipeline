"""Gemini TTS adapter offline tests — mocked PCM, no network."""

from __future__ import annotations

import ast
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from voice_sync.gemini_tts import (
    DIRECTING_STYLE_PREFIX,
    GEMINI_RAW_SAMPLE_RATE_HZ,
    LUFS_TOLERANCE_LU,
    OUTPUT_CHANNELS,
    OUTPUT_SAMPLE_RATE_HZ,
    TARGET_LUFS,
    GeminiTtsAdapter,
    load_gemini_tts_config,
    measure_integrated_lufs,
    pcm_to_wav_bytes,
    process_raw_gemini_pcm,
    wav_bytes_to_pcm,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "voice_sync" / "gemini_tts.py"
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "aiohttp", "ftplib"}
REPO_ROOT = Path(__file__).resolve().parents[3]
PROVIDERS = REPO_ROOT / "providers.yaml"


def test_module_has_no_network_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                assert base not in _BANNED_IMPORTS
        if isinstance(node, ast.ImportFrom) and node.module:
            base = node.module.split(".")[0]
            assert base not in _BANNED_IMPORTS


def test_loads_model_ids_from_providers_yaml() -> None:
    config = load_gemini_tts_config(PROVIDERS)
    assert config.provider_id == "tts"
    assert config.primary_model_id == "gemini-3.8-flash-tts"
    assert config.alternate_model_id == "flash-lite-tts"


def _sine_pcm(duration_s: float, freq_hz: float, gain: float, sample_rate: int) -> bytes:
    n = int(duration_s * sample_rate)
    samples: list[int] = []
    for i in range(n):
        normalized = 0.35 * gain * math.sin(2 * math.pi * freq_hz * i / sample_rate)
        samples.append(int(max(-32767, min(32767, round(normalized * 32767)))))
    return struct.pack(f"<{len(samples)}h", *samples)


@dataclass
class MockTtsClient:
    gain: float = 1.0
    calls: list[tuple[str, str, int]] = field(default_factory=list)

    def synthesize(self, *, model_id: str, text: str, sample_rate_hz: int) -> bytes:
        self.calls.append((model_id, text, sample_rate_hz))
        assert sample_rate_hz == GEMINI_RAW_SAMPLE_RATE_HZ
        return _sine_pcm(0.25, 440.0, self.gain, sample_rate_hz)


def test_style_prefix_applied_to_every_chunk() -> None:
    client = MockTtsClient()
    adapter = GeminiTtsAdapter.from_providers(client, providers_path=PROVIDERS)
    adapter.synthesize_chunks(["Alpha.", "Beta."])
    assert len(client.calls) == 2
    for _, text, _ in client.calls:
        assert text.startswith(DIRECTING_STYLE_PREFIX)
    assert client.calls[0][1].endswith("Alpha.")
    assert client.calls[1][1].endswith("Beta.")


def test_output_is_48khz_stereo_pcm() -> None:
    client = MockTtsClient()
    adapter = GeminiTtsAdapter.from_providers(client, providers_path=PROVIDERS)
    chunk = adapter.synthesize_chunk("Scene beat.")
    assert chunk.sample_rate_hz == OUTPUT_SAMPLE_RATE_HZ
    assert chunk.channels == OUTPUT_CHANNELS
    samples = len(chunk.pcm_s16le) // 2
    assert samples == samples // 2 * 2
    wav = pcm_to_wav_bytes(
        chunk.pcm_s16le,
        sample_rate_hz=chunk.sample_rate_hz,
        channels=chunk.channels,
    )
    pcm, rate, ch = wav_bytes_to_pcm(wav)
    assert rate == OUTPUT_SAMPLE_RATE_HZ
    assert ch == OUTPUT_CHANNELS
    assert pcm == chunk.pcm_s16le


def test_resample_doubles_frame_count() -> None:
    raw = _sine_pcm(0.1, 220.0, 1.0, GEMINI_RAW_SAMPLE_RATE_HZ)
    mastered = process_raw_gemini_pcm(raw)
    raw_frames = len(raw) // 2
    out_frames = len(mastered.pcm_s16le) // 2 // OUTPUT_CHANNELS
    assert out_frames == pytest.approx(raw_frames * 2, rel=0.02)


def test_chunk_lufs_within_target_band() -> None:
    client = MockTtsClient(gain=0.35)
    adapter = GeminiTtsAdapter.from_providers(client, providers_path=PROVIDERS)
    chunk = adapter.synthesize_chunk("Loudness pass.")
    assert chunk.integrated_lufs == pytest.approx(TARGET_LUFS, abs=LUFS_TOLERANCE_LU)
    measured = measure_integrated_lufs(chunk.pcm_s16le, chunk.sample_rate_hz, chunk.channels)
    assert measured == pytest.approx(TARGET_LUFS, abs=LUFS_TOLERANCE_LU)


def test_different_input_gains_match_after_normalization() -> None:
    low = MockTtsClient(gain=0.18)
    high = MockTtsClient(gain=2.4)
    adapter_low = GeminiTtsAdapter.from_providers(low, providers_path=PROVIDERS)
    adapter_high = GeminiTtsAdapter.from_providers(high, providers_path=PROVIDERS)
    chunk_low = adapter_low.synthesize_chunk("Same script.")
    chunk_high = adapter_high.synthesize_chunk("Same script.")
    assert chunk_low.integrated_lufs == pytest.approx(chunk_high.integrated_lufs, abs=0.05)
    assert chunk_low.integrated_lufs == pytest.approx(TARGET_LUFS, abs=LUFS_TOLERANCE_LU)
    assert chunk_high.integrated_lufs == pytest.approx(TARGET_LUFS, abs=LUFS_TOLERANCE_LU)


def test_uses_primary_model_from_registry() -> None:
    client = MockTtsClient()
    adapter = GeminiTtsAdapter.from_providers(client, providers_path=PROVIDERS)
    chunk = adapter.synthesize_chunk("Model check.")
    assert chunk.model_id == "gemini-3.8-flash-tts"
    assert client.calls[0][0] == "gemini-3.8-flash-tts"