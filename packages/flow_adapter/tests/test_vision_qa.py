import importlib.util
import subprocess
import sys
import time
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "flow_adapter" / "vision_qa.py"
_SPEC = importlib.util.spec_from_file_location("tc157_qa", _PATH)
assert _SPEC and _SPEC.loader
qa = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = qa
_SPEC.loader.exec_module(qa)


def test_clean_blank_and_fail_closed(tmp_path: Path):
    clean = tmp_path / "clean.mp4"
    blank = tmp_path / "blank.mp4"
    _make(clean, "0xE9E2D2")
    _make(blank, "0x000000")
    started = time.perf_counter()

    def judge(frames):
        assert len(frames) == 3
        return {"passed": True, "failure_codes": [], "confidence": 0.8, "retry_hint": ""}

    verdict = qa.review(str(clean), "hero", str(tmp_path / "frames"), judge)
    assert verdict.passed is True
    assert verdict.state == "qa_passed"
    assert time.perf_counter() - started < 2.0
    blocked = qa.review(str(blank), "blank", str(tmp_path / "frames"), judge)
    assert blocked.passed is False
    assert "BLANK_FRAME" in blocked.failure_codes

    def down(_frames):
        raise RuntimeError("rate limit")

    closed = qa.review(str(clean), "down", str(tmp_path / "frames"), down)
    assert closed.state == "PENDING_MANUAL_SPOT_CHECK"
    assert closed.passed is False


def _make(path: Path, color: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=1:r=30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )
