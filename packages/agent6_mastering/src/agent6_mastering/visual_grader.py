"""One grain pass on synthetic scenes. FOIA bytes are copied through."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def grade(segments: list[dict], out_dir: str) -> dict:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    rows = []
    graded = []
    for segment in segments:
        if segment.get("is_foia") or segment.get("exempt_from_grain"):
            dest = root / f"{segment['scene_id']}.mp4"
            shutil.copyfile(segment["path"], dest)
            rows.append({"scene_id": segment["scene_id"], "path": dest.as_posix(), "grained": False})
        else:
            graded.append(segment)
    if graded:
        plate = root / "master_video_silent.mp4"
        _grain([item["path"] for item in graded], plate)
        for item in graded:
            rows.append({"scene_id": item["scene_id"], "path": plate.as_posix(), "grained": True})
    manifest = {"remotion_grain_applied": False, "segments": rows}
    (root / "scene_grade_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    if manifest["remotion_grain_applied"]:
        raise RuntimeError("a second grain pass was requested")
    return manifest


def _grain(paths: list[str], out: Path) -> None:
    script = out.with_suffix(".txt")
    lines = ["ffconcat version 1.0", *[f"file '{Path(path).as_posix()}'" for path in paths]]
    script.write_text("\n".join(lines) + "\n", encoding="utf8")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(script),
            "-vf", "noise=alls=4:allf=t+u,vignette=PI/6",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p", "-an",
            str(out),
        ],
        check=True, capture_output=True,
    )


def sha256(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
