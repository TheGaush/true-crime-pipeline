"""Spectral and header checks for the ten procedural documentary cues."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import wave
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

_MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "python_motion" / "sfx_synth.py"
_SPEC = importlib.util.spec_from_file_location("tc_task137_sfx_synth", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_sfx = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _sfx
_SPEC.loader.exec_module(_sfx)


def synth():
    return _sfx.SfxSynthesizer()


def ask(cue: str, **kwargs):
    return _sfx.SfxRequest(cue_type=cue, **kwargs)


def test_all_ten_cues_are_48k_pcm_under_the_peak_ceiling(tmp_path: Path):
    engine = synth()
    hashes: dict[str, str] = {}
    for cue in _sfx.CUE_IDS:
        first = engine.synthesize(ask(cue, seed=7, cache_dir=str(tmp_path)))
        second = engine.synthesize(ask(cue, seed=7, cache_dir=str(tmp_path)))
        assert first.sha256 == second.sha256
        assert second.cache_hit is True
        assert first.sample_rate_hz == 48_000
        assert first.pcm.dtype == np.int16
        assert first.pcm.ndim == 1
        assert first.peak_dbfs <= -3.0
        assert first.dc_offset < 0.001
        assert np.all(np.isfinite(first.pcm))
        rate, read = wavfile.read(first.path)
        assert rate == 48_000
        assert read.dtype == np.int16
        assert np.array_equal(read, first.pcm)
        with wave.open(first.path, "rb") as header:
            assert header.getnchannels() == 1
            assert header.getsampwidth() == 2
            assert header.getframerate() == 48_000
            assert header.getcomptype() == "NONE"
        hashes[cue] = first.sha256
        assert f"__s7__d{first.duration_ms}__" in Path(first.path).name
    assert len(hashes) == 10
    assert len(set(hashes.values())) == 10


def test_aliases_and_unknown_cues_do_not_crash(caplog, tmp_path: Path):
    engine = synth()
    with caplog.at_level(logging.WARNING, logger="python_motion.sfx"):
        gavel = engine.synthesize(ask("gavel", seed=3, duration_ms=180, cache_dir=str(tmp_path)))
        click = engine.synthesize(ask("click", seed=3, duration_ms=36, cache_dir=str(tmp_path)))
        mystery = engine.synthesize(ask("mystery_horn", seed=3, duration_ms=420, cache_dir=str(tmp_path)))
        siren = engine.synthesize(ask("siren", seed=3, duration_ms=420, cache_dir=str(tmp_path)))
    stamp = engine.synthesize(ask("stamp_thud", seed=3, duration_ms=180, cache_dir=str(tmp_path)))
    key = engine.synthesize(ask("typewriter_key", seed=3, duration_ms=36, cache_dir=str(tmp_path)))
    paper = engine.synthesize(ask("paper_slide", seed=3, duration_ms=420, cache_dir=str(tmp_path)))
    assert gavel.cue_type == "stamp_thud"
    assert gavel.sha256 == stamp.sha256
    assert click.cue_type == "typewriter_key"
    assert click.sha256 == key.sha256
    assert mystery.cue_type == "paper_slide"
    assert mystery.sha256 == paper.sha256
    assert siren.cue_type == "paper_slide"
    assert siren.sha256 == paper.sha256
    assert any(item["code"] == "CUE_ALIAS" for item in gavel.warnings)
    assert any(item["code"] == "UNKNOWN_CUE" for item in mystery.warnings)
    assert any(item["code"] == "FORBIDDEN_TIMBRE" for item in siren.warnings)
    codes = {json.loads(rec.message)["code"] for rec in caplog.records}
    assert {"CUE_ALIAS", "UNKNOWN_CUE", "FORBIDDEN_TIMBRE"} <= codes


def test_spectral_character_of_bass_beep_drone_and_typewriter():
    engine = synth()
    bass = engine.synthesize(ask("bass_drop_hit", seed=1, intensity=1.0))
    beep = engine.synthesize(ask("police_beep_clean", seed=1))
    drone = engine.synthesize(ask("tension_drone_pulse", seed=1))
    key = engine.synthesize(ask("typewriter_key", seed=1, duration_ms=36))
    whoosh = engine.synthesize(ask("subtle_whoosh", seed=1))
    assert _sfx.spectral_peak_hz(bass.pcm) < 150.0
    assert 900.0 <= _sfx.spectral_peak_hz(beep.pcm) <= 1100.0
    assert _sfx.spectral_peak_hz(drone.pcm) < 250.0
    assert _half_peak_delta(beep.pcm) < 20.0
    assert _half_peak_delta(drone.pcm) < 20.0
    assert _high_band_ratio(key.pcm) > _high_band_ratio(bass.pcm)
    assert _sfx.spectral_peak_hz(whoosh.pcm) > _sfx.spectral_peak_hz(bass.pcm)


def test_short_typewriter_keeps_a_one_millisecond_onset():
    cue = synth().synthesize(ask("typewriter_key", duration_ms=25, seed=9))
    assert cue.pcm.shape[0] == 25 * 48
    onset = cue.pcm[:48]
    assert int(np.max(np.abs(onset))) > 0
    assert abs(int(cue.pcm[-1])) < abs(int(np.max(cue.pcm))) 


def test_stereo_header_and_seed_stability():
    engine = synth()
    left = engine.synthesize(ask("map_pin_pop", seed=11, channels=2))
    again = engine.synthesize(ask("map_pin_pop", seed=11, channels=2))
    other = engine.synthesize(ask("map_pin_pop", seed=12, channels=2))
    assert left.sha256 == again.sha256
    assert left.sha256 != other.sha256
    assert left.pcm.shape[1] == 2
    assert left.peak_dbfs <= -3.0
    assert left.dc_offset < 0.001
    assert np.array_equal(left.pcm[:, 0], left.pcm[:, 1])


def test_ffprobe_reads_pcm_s16le(tmp_path: Path):
    cue = synth().synthesize(ask("camera_shutter", seed=2, cache_dir=str(tmp_path)))
    import shutil
    import subprocess

    ffprobe = shutil.which("ffprobe")
    assert ffprobe is not None
    probed = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "stream=codec_name,sample_rate,channels", "-of", "json", cue.path],
        check=True,
        capture_output=True,
        text=True,
    )
    stream = json.loads(probed.stdout)["streams"][0]
    assert stream["codec_name"] == "pcm_s16le"
    assert stream["sample_rate"] == "48000"
    assert stream["channels"] == 1


def _half_peak_delta(pcm: np.ndarray) -> float:
    mid = pcm.shape[0] // 2
    return abs(_sfx.spectral_peak_hz(pcm[:mid]) - _sfx.spectral_peak_hz(pcm[mid:]))


def _high_band_ratio(pcm: np.ndarray) -> float:
    spectrum = np.abs(np.fft.rfft(pcm.astype(np.float64) * np.hanning(pcm.shape[0])))
    freqs = np.fft.rfftfreq(pcm.shape[0], 1.0 / 48_000)
    high = float(np.sum(spectrum[freqs >= 2000.0]))
    low = float(np.sum(spectrum[freqs < 200.0]))
    return high / max(low, 1e-9)
