import importlib.util
import subprocess
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "flow_adapter" / "drop_ingestor.py"
_SPEC = importlib.util.spec_from_file_location("tc156_drop", _PATH)
assert _SPEC and _SPEC.loader
drop = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = drop
_SPEC.loader.exec_module(drop)


def test_conform_duplicate_and_corrupt(tmp_path: Path):
    source = tmp_path / "src"
    source.mkdir()
    good = source / "good.mp4"
    short = source / "short.mp4"
    _make(good, 1.0, 24, "1280x720")
    _make(short, 0.3, 30, "1280x720")
    out = tmp_path / "flow_ingested"
    receipt = drop.ingest(str(good), "hero", str(out), 1.0)
    assert receipt.width == 1920 and receipt.height == 1080 and receipt.fps == "30/1"
    assert good.stat().st_size > 0
    try:
        drop.ingest(str(good), "other", str(out), 1.0)
        assert False
    except drop.DuplicateClipDropError:
        pass
    try:
        drop.ingest(str(short), "bad", str(out), 1.0)
        assert False
    except drop.DropRejectedError:
        pass
    empty = source / "empty.mp4"
    empty.write_bytes(b"")
    try:
        drop.ingest(str(empty), "empty", str(out), 1.0)
        assert False
    except drop.DropRejectedError as error:
        assert "incomplete" in str(error).lower() or "Download incomplete" in str(error)


def _make(path: Path, seconds: float, fps: int, size: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0xE9E2D2:s={size}:d={seconds}:r={fps}", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )
