"""Google Vids optional TTS adapter offline tests — injected PCM, no FFmpeg."""

from __future__ import annotations

import ast
import math
import struct
from dataclasses import dataclass
from pathlib import Path

import pytest

from voice_sync.google_vids_tts import (
    GOOGLE_VIDS_PROVIDER_ID,
    LUFS_TOLERANCE_LU,
    OUTPUT_CHANNELS,
    OUTPUT_SAMPLE_RATE_HZ,
    TARGET_LUFS,
    GoogleVidsNotSelectedError,
    GoogleVidsSelection,
    GoogleVidsTtsAdapter,
    MissingAudioStreamError,
    format_bracket_tag_script,
    measure_integrated_lufs,
    normalize_export_pcm,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "voice_sync" / "google_vids_tts.py"
_BANNED_IMPORTS = {"socket", "urllib", "http", "requests", "httpx", "subprocess"}


def test_module_has_no_network_or_subprocess_imports() -> None:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                assert root not in _BANNED_IMPORTS
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".", 1)[0]
            assert root not in _BANNED_IMPORTS


def test_format_bracket_tag_script_splits_directions() -> None:
    raw = "[calmly] The jury returned a verdict. [dramatically] But the story was not over."
    out = format_bracket_tag_script(raw)
    assert "[Direction: calmly]" in out
    assert "The jury returned a verdict." in out
    assert "[Direction: dramatically]" in out
    assert "But the story was not over." in out
    assert out.index("[Direction: calmly]") < out.index("[Direction: dramatically]")


def test_format_bracket_tag_script_preserves_neutral_lead_in() -> None:
    raw = "Opening context. [calmly] Then the narration begins."
    out = format_bracket_tag_script(raw)
    assert "[Direction: neutral]" in out
    assert "Opening context." in out


@pytest.mark.parametrize("tag", ["calmly", "dramatically", "measured", "whisper"])
def test_format_bracket_tag_script_normalizes_tag_case(tag: str) -> None:
    raw = f"[{tag.upper()}] A single beat."
    out = format_bracket_tag_script(raw)
    assert f"[Direction: {tag.lower()}]" in out


def _sine_pcm(
    *,
    sample_rate_hz: int,
    duration_s: float,
    frequency_hz: float,
    amplitude: float,
    channels: int,
) -> bytes:
    frame_count = int(sample_rate_hz * duration_s)
    frames: list[int] = []
    for i in range(frame_count):
        t = i / sample_rate_hz
        sample = int(round(amplitude * 32767.0 * math.sin(2.0 * math.pi * frequency_hz * t)))
        for _ in range(channels):
            frames.append(sample)
    return struct.pack(f"<{len(frames)}h", *frames)


@dataclass
class _Stream:
    pcm: bytes | None

    def read_pcm(self, export_bytes: bytes) -> bytes | None:
        _ = export_bytes
        return self.pcm


def test_extract_voiceover_requires_explicit_selection() -> None:
    adapter = GoogleVidsTtsAdapter()
    export = b"synthetic-mp4-bytes"
    with pytest.raises(GoogleVidsNotSelectedError):
        adapter.extract_voiceover(
            selection=GoogleVidsSelection(explicit=False),
            export_bytes=export,
            audio_stream=_Stream(pcm=_sine_pcm(
                sample_rate_hz=48000,
                duration_s=0.25,
                frequency_hz=440.0,
                amplitude=0.2,
                channels=2,
            )),
            formatted_script="",
        )


def test_extract_voiceover_raises_when_no_audio_stream() -> None:
    adapter = GoogleVidsTtsAdapter()
    with pytest.raises(MissingAudioStreamError):
        adapter.extract_voiceover(
            selection=GoogleVidsSelection(explicit=True),
            export_bytes=b"video-only-export",
            audio_stream=_Stream(pcm=None),
            formatted_script="",
        )


def test_extract_voiceover_masters_to_target_lufs() -> None:
    adapter = GoogleVidsTtsAdapter()
    quiet = _sine_pcm(
        sample_rate_hz=48000,
        duration_s=0.4,
        frequency_hz=300.0,
        amplitude=0.05,
        channels=2,
    )
    script = adapter.format_script("[calmly] Witness testimony follows.")
    result = adapter.extract_voiceover(
        selection=GoogleVidsSelection(explicit=True),
        export_bytes=b"fixture-export",
        audio_stream=_Stream(pcm=quiet),
        formatted_script=script,
    )
    assert result.sample_rate_hz == OUTPUT_SAMPLE_RATE_HZ
    assert result.channels == OUTPUT_CHANNELS
    assert result.provider_id == GOOGLE_VIDS_PROVIDER_ID
    assert result.formatted_script == script
    assert abs(result.integrated_lufs - TARGET_LUFS) <= LUFS_TOLERANCE_LU
    remeasured = measure_integrated_lufs(
        result.pcm_s16le, OUTPUT_SAMPLE_RATE_HZ, OUTPUT_CHANNELS
    )
    assert abs(remeasured - TARGET_LUFS) <= LUFS_TOLERANCE_LU


def test_normalize_export_pcm_resamples_mono_24k_to_stereo_48k() -> None:
    mono = _sine_pcm(
        sample_rate_hz=24000,
        duration_s=0.2,
        frequency_hz=500.0,
        amplitude=0.15,
        channels=1,
    )
    pcm, lufs = normalize_export_pcm(mono, source_sample_rate_hz=24000, source_channels=1)
    assert len(pcm) == int(0.2 * OUTPUT_SAMPLE_RATE_HZ) * OUTPUT_CHANNELS * 2
    assert math.isfinite(lufs)
    assert abs(lufs - TARGET_LUFS) <= LUFS_TOLERANCE_LU


def test_two_exports_with_different_gain_match_after_normalization() -> None:
    adapter = GoogleVidsTtsAdapter()
    base = _sine_pcm(
        sample_rate_hz=48000,
        duration_s=0.35,
        frequency_hz=220.0,
        amplitude=0.08,
        channels=2,
    )
    loud = _sine_pcm(
        sample_rate_hz=48000,
        duration_s=0.35,
        frequency_hz=220.0,
        amplitude=0.35,
        channels=2,
    )
    script = adapter.format_script("[calmly] Shared mastering target.")
    quiet_out = adapter.extract_voiceover(
        selection=GoogleVidsSelection(explicit=True),
        export_bytes=b"quiet",
        audio_stream=_Stream(pcm=base),
        formatted_script=script,
    )
    loud_out = adapter.extract_voiceover(
        selection=GoogleVidsSelection(explicit=True),
        export_bytes=b"loud",
        audio_stream=_Stream(pcm=loud),
        formatted_script=script,
    )
    assert abs(quiet_out.integrated_lufs - loud_out.integrated_lufs) <= 0.25