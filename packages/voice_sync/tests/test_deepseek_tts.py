"""DeepSeek Speech TTS failover adapter tests — mocked HTTP only."""

from __future__ import annotations

import ast
import math
import struct
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from voice_sync.deepseek_tts import (
    DIRECTING_STYLE_PREFIX,
    DEEPSEEK_RAW_SAMPLE_RATE_HZ,
    LUFS_TOLERANCE_LU,
    OUTPUT_CHANNELS,
    OUTPUT_SAMPLE_RATE_HZ,
    TARGET_LUFS,
    DeepSeekTtsAdapter,
    DeepSeekTtsConfig,
    HttpResponse,
    load_deepseek_tts_config,
    measure_integrated_lufs,
    pcm_to_wav_bytes,
    process_raw_deepseek_pcm,
    wav_bytes_to_pcm,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "voice_sync" / "deepseek_tts.py"
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


def test_loads_failover_model_and_rates_from_providers_yaml() -> None:
    config = load_deepseek_tts_config(PROVIDERS)
    assert config.billing_provider_id == "deepseek_chat"
    assert config.speech_model_id == "DeepSeek-V4.1-Flash-1017"
    assert config.failover_model_id == "flash-lite-tts"
    assert config.conservative_micro_usd_per_char > 0


def _sine_pcm(duration_s: float, freq_hz: float, gain: float, sample_rate: int) -> bytes:
    n = int(duration_s * sample_rate)
    samples = [
        int(
            max(
                -32767,
                min(32767, round(28000 * gain * math.sin(2 * math.pi * freq_hz * i / sample_rate))),
            )
        )
        for i in range(n)
    ]
    return struct.pack(f"<{len(samples)}h", *samples)


@dataclass
class MockHttpClient:
    """Fails the second primary-model request to force mid-episode failover."""

    config: DeepSeekTtsConfig
    fail_primary_after: int = 1
    calls: list[dict] = field(default_factory=list)
    _primary_successes: int = 0

    def post(self, *, path: str, json_body: dict) -> HttpResponse:
        self.calls.append({"path": path, **json_body})
        assert path == "/v1/audio/speech"
        model = json_body["model"]
        gain = 0.9 if model == self.config.speech_model_id else 0.55
        if model == self.config.speech_model_id:
            self._primary_successes += 1
            if self._primary_successes > self.fail_primary_after:
                return HttpResponse(status_code=503, body=b"")
        pcm = _sine_pcm(0.2, 440.0 if model == self.config.speech_model_id else 360.0, gain, DEEPSEEK_RAW_SAMPLE_RATE_HZ)
        return HttpResponse(status_code=200, body=pcm)


def test_mid_episode_failover_resynth_prior_chunks_same_failover_voice() -> None:
    config = load_deepseek_tts_config(PROVIDERS)
    http = MockHttpClient(config=config, fail_primary_after=1)
    adapter = DeepSeekTtsAdapter(http=http, config=config)
    result = adapter.synthesize_episode("ep-064", ["Chunk one beat.", "Chunk two beat."])

    assert result.engaged_failover is True
    assert len(result.chunks) == 2
    assert all(not chunk.needs_resynthesis for chunk in result.chunks)
    failover_voice = adapter.failover_voice_id("ep-064")
    assert result.voice_id == failover_voice
    assert result.chunks[0].voice_id == failover_voice
    assert result.chunks[1].voice_id == failover_voice
    assert result.chunks[0].model_id == config.failover_model_id
    assert result.chunks[1].model_id == config.failover_model_id

    primary_calls = [c for c in http.calls if c["model"] == config.speech_model_id]
    failover_calls = [c for c in http.calls if c["model"] == config.failover_model_id]
    assert len(primary_calls) == 2
    assert len(failover_calls) == 2
    for call in failover_calls:
        assert call["voice"] == failover_voice


def test_style_prefix_on_http_payload() -> None:
    config = load_deepseek_tts_config(PROVIDERS)

    @dataclass
    class OkHttp:
        calls: list[dict] = field(default_factory=list)

        def post(self, *, path: str, json_body: dict) -> HttpResponse:
            self.calls.append(json_body)
            pcm = _sine_pcm(0.1, 220.0, 0.8, DEEPSEEK_RAW_SAMPLE_RATE_HZ)
            return HttpResponse(status_code=200, body=pcm)

    http = OkHttp()
    adapter = DeepSeekTtsAdapter(http=http, config=config)
    session = adapter.new_session("ep-style")
    adapter.synthesize_chunk(session, 0, "Cold open.")
    assert http.calls[0]["input"].startswith(DIRECTING_STYLE_PREFIX)
    assert http.calls[0]["input"].endswith("Cold open.")


def test_output_is_48khz_stereo_pcm_and_lufs() -> None:
    config = load_deepseek_tts_config(PROVIDERS)

    @dataclass
    class OkHttp:
        def post(self, *, path: str, json_body: dict) -> HttpResponse:
            pcm = _sine_pcm(0.15, 330.0, 0.4, DEEPSEEK_RAW_SAMPLE_RATE_HZ)
            return HttpResponse(status_code=200, body=pcm)

    adapter = DeepSeekTtsAdapter(http=OkHttp(), config=config)
    session = adapter.new_session("ep-master")
    record = adapter.synthesize_chunk(session, 0, "Mastering check.")
    assert record.audio is not None
    chunk = record.audio
    assert chunk.sample_rate_hz == OUTPUT_SAMPLE_RATE_HZ
    assert chunk.channels == OUTPUT_CHANNELS
    assert chunk.integrated_lufs == pytest.approx(TARGET_LUFS, abs=LUFS_TOLERANCE_LU)
    wav = pcm_to_wav_bytes(
        chunk.pcm_s16le,
        sample_rate_hz=chunk.sample_rate_hz,
        channels=chunk.channels,
    )
    pcm, rate, ch = wav_bytes_to_pcm(wav)
    assert rate == OUTPUT_SAMPLE_RATE_HZ
    assert ch == OUTPUT_CHANNELS
    measured = measure_integrated_lufs(pcm, rate, ch)
    assert measured == pytest.approx(TARGET_LUFS, abs=LUFS_TOLERANCE_LU)


def test_process_raw_pcm_resamples_to_48k() -> None:
    raw = _sine_pcm(0.1, 200.0, 1.0, DEEPSEEK_RAW_SAMPLE_RATE_HZ)
    mastered = process_raw_deepseek_pcm(raw)
    raw_frames = len(raw) // 2
    out_frames = len(mastered.pcm_s16le) // 2 // OUTPUT_CHANNELS
    assert out_frames == pytest.approx(raw_frames * 2, rel=0.02)


def test_single_episode_voice_id_without_failover() -> None:
    config = load_deepseek_tts_config(PROVIDERS)

    @dataclass
    class OkHttp:
        def post(self, *, path: str, json_body: dict) -> HttpResponse:
            pcm = _sine_pcm(0.1, 180.0, 0.7, DEEPSEEK_RAW_SAMPLE_RATE_HZ)
            return HttpResponse(status_code=200, body=pcm)

    adapter = DeepSeekTtsAdapter(http=OkHttp(), config=config)
    result = adapter.synthesize_episode("ep-stable", ["Only chunk."])
    primary_voice = adapter.primary_voice_id("ep-stable")
    assert result.engaged_failover is False
    assert result.voice_id == primary_voice
    assert result.chunks[0].voice_id == primary_voice