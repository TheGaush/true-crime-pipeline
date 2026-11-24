import array
import sys
import wave
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))
from integration_bridge.narration import active_line, caption_lines, script_text
from integration_bridge.pipeline_run import workflow_report
from integration_bridge.voice_track import render_narration


def test_script_is_spoken_on_the_matching_scene():
    assert "illustrative" in active_line(1.0).lower()
    assert "silhouette" in active_line(14.0).lower()
    assert "porch camera" in active_line(36.0).lower()
    assert "name covered" in active_line(58.0).lower()
    assert "synthetic reconstruction" in active_line(80.0).lower()
    assert "living minor" not in script_text().lower()
    assert len(caption_lines(80.0)) >= 2


def test_local_voice_is_ninety_seconds_and_not_a_tone(tmp_path: Path):
    info = render_narration(str(tmp_path / "narration.wav"))
    assert info["engine"] in {"flite", "bundled"}
    assert info["lines"][0].startswith("An illustrative case file.")
    with wave.open(str(tmp_path / "narration.wav")) as handle:
        assert handle.getnframes() / handle.getframerate() == 90
        rate = handle.getframerate()
        handle.setpos(int(0.1 * rate))
        quiet = _rms(handle.readframes(int(0.3 * rate)))
        handle.setpos(int(1.0 * rate))
        spoken = _rms(handle.readframes(int(0.4 * rate)))
    assert quiet < 50
    assert spoken > 500
    report = workflow_report()
    assert report[3]["live"] is False
    assert report[3]["narration"] == script_text()


def test_missing_flite_uses_the_bundled_take(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("integration_bridge.voice_track._flite_available", lambda: False)
    info = render_narration(str(tmp_path / "narration.wav"))
    assert info["engine"] == "bundled"
    with wave.open(str(tmp_path / "narration.wav")) as handle:
        assert handle.getnframes() / handle.getframerate() == 90


def test_paid_keys_do_not_place_a_call(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "present")
    monkeypatch.setenv("GEMINI_API_KEY", "present")
    report = workflow_report()
    assert report[3]["live"] is False
    assert report[3]["keys_ready"] is True
    assert report[4]["live"] is False
    assert report[4]["keys_ready"] is True


def _rms(payload: bytes) -> float:
    samples = array.array("h")
    samples.frombytes(payload)
    if not samples:
        return 0.0
    return (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
