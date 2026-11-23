import importlib.util
import subprocess
import sys
from pathlib import Path

_PATH = Path(__file__).resolve().parents[1] / "src" / "agent6_mastering" / "visual_grader.py"
_SPEC = importlib.util.spec_from_file_location("tc167_grade", _PATH)
assert _SPEC and _SPEC.loader
grade = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = grade
_SPEC.loader.exec_module(grade)


def test_foia_is_copied_and_synthetic_is_grained(tmp_path: Path):
    foia = tmp_path / "foia.mp4"
    code = tmp_path / "code.mp4"
    _make(foia, "0x3A4F66")
    _make(code, "0xE9E2D2")
    manifest = grade.grade(
        [
            {"scene_id": "body", "path": str(foia), "is_foia": True, "exempt_from_grain": True},
            {"scene_id": "draw", "path": str(code), "is_foia": False},
        ],
        str(tmp_path / "out"),
    )
    copied = next(row for row in manifest["segments"] if row["scene_id"] == "body")
    assert grade.sha256(copied["path"]) == grade.sha256(str(foia))
    assert copied["grained"] is False
    assert manifest["remotion_grain_applied"] is False
    plate = tmp_path / "out" / "master_video_silent.mp4"
    assert plate.is_file()
    assert grade.sha256(str(plate)) != grade.sha256(str(code))


def _make(path: Path, color: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x180:d=0.3:r=30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )
