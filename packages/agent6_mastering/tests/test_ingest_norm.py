import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "ingest_norm.py"
_SPEC = importlib.util.spec_from_file_location("tc163_norm", _PATH)
assert _SPEC and _SPEC.loader
norm = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = norm
_SPEC.loader.exec_module(norm)


def test_mixed_rates_share_one_timeline(tmp_path: Path):
    assert norm.expected_frames(1200) == 36_000
    specs = [
        ("body", "FOIA_REAL_FOOTAGE", 29.97, "640x360"),
        ("code", "CODE_STICKMAN", 30, "1920x1080"),
        ("phone", "FOIA_REAL_FOOTAGE", 60, "1080x1920"),
    ]
    segments = []
    for scene_id, engine, fps, size in specs:
        source = tmp_path / f"{scene_id}.mp4"
        _make(source, fps, size)
        segments.append(norm.normalize(str(source), scene_id, str(tmp_path / "norm"), engine, 1.0))
    assert all(item.nb_frames == 30 for item in segments)
    assert segments[0].is_foia and segments[0].exempt_from_grain
    assert segments[1].is_foia is False
    phone = _frame(segments[2].path, 0)
    assert phone.getpixel((8, 540)) != phone.getpixel((960, 540))
    script = tmp_path / "concat.txt"
    lines = ["ffconcat version 1.0"]
    for item in segments:
        lines.append(f"file '{item.path}'")
    script.write_text("\n".join(lines) + "\n", encoding="utf8")
    joined = tmp_path / "joined.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(script), "-c", "copy", str(joined)],
        check=True, capture_output=True,
    )
    frames = int(_video(joined)["nb_frames"])
    assert frames == 90
    assert abs(frames / 30 - 3.0) < 0.015
    norm.write_manifest(segments, str(tmp_path / "timeline.json"))
    saved = json.loads((tmp_path / "timeline.json").read_text(encoding="utf8"))
    assert saved["segments"][0]["exempt_from_grain"] is True


def _make(path: Path, fps: float, size: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x3A4F66:s={size}:d=1:r={fps}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def _video(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames,r_frame_rate", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)["streams"][0]


def _frame(path: str, index: int):
    from PIL import Image
    import io

    result = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-vf", f"select=eq(n\\,{index})", "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True,
    )
    return Image.open(io.BytesIO(result.stdout))
