import importlib.util
import subprocess
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "final_muxer.py"
_SPEC = importlib.util.spec_from_file_location("tc168_mux", _PATH)
assert _SPEC and _SPEC.loader
mux = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = mux
_SPEC.loader.exec_module(mux)


def test_mux_keeps_rate_color_and_chapters(tmp_path: Path):
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0xE9E2D2:s=640x360:d=1:r=30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(video)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000:duration=1", "-c:a", "pcm_s16le", str(audio)],
        check=True, capture_output=True,
    )
    info = mux.mux(str(video), str(audio), [{"start_ms": 0, "end_ms": 1000, "title": "Rue #1; case"}], str(tmp_path / "final.mp4"))
    assert info["r_frame_rate"] == "30/1"
    assert info["sample_rate"] == "48000"
    assert info["color_space"] == "bt709"
    assert abs(info["duration"] - 1.0) <= 0.05
    assert "Rue #1" in (tmp_path / "chapters.txt").read_text(encoding="utf8")
    assert "\\#" in (tmp_path / "chapters.ffmeta").read_text(encoding="utf8")
