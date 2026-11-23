import importlib.util
import subprocess
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "track_norm.py"
_SPEC = importlib.util.spec_from_file_location("tc165_norm", _PATH)
assert _SPEC and _SPEC.loader
norm = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = norm
_SPEC.loader.exec_module(norm)


def test_tone_is_measured_and_silence_short_circuits(tmp_path: Path):
    tone = tmp_path / "tone.wav"
    quiet = tmp_path / "quiet.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=3", "-c:a", "pcm_s16le", str(tone)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=48000", "-t", "0.4", "-c:a", "pcm_s16le", str(quiet)],
        check=True, capture_output=True,
    )
    spoken = norm.normalize_stem(str(tone), 1, str(tmp_path / "track1.wav"))
    assert spoken["silent"] is False
    assert abs(spoken["integrated_lufs"] - (-16.0)) <= 1.0
    silent = norm.normalize_stem(str(quiet), 2, str(tmp_path / "track2.wav"))
    assert silent["silent"] is True
    assert Path(silent["path"]).is_file()
