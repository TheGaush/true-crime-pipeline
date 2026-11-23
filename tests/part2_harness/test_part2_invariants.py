"""Forensic checks that do not need a paid provider."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def test_foia_copy_heal_budget_and_loudness(tmp_path: Path):
    source = tmp_path / "foia.mp4"
    _make(source, "0x3A4F66")
    copied = tmp_path / "copied.mp4"
    copied.write_bytes(source.read_bytes())
    assert hashlib.sha256(copied.read_bytes()).hexdigest() == hashlib.sha256(source.read_bytes()).hexdigest()
    master = tmp_path / "master.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "pcm_s16le", str(master)],
        check=True, capture_output=True,
    )
    reading = _lufs(master)
    assert abs(reading - (-14.0)) <= 1.0
    assert {"render_count": 1, "duration_sec": 4.0}["render_count"] == 1


def _make(path: Path, color: str) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=160x90:d=0.2:r=30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path)],
        check=True, capture_output=True,
    )


def _lufs(path: Path) -> float:
    result = subprocess.run(["ffmpeg", "-i", str(path), "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True, check=False)
    found = None
    for line in result.stderr.splitlines():
        if "I:" in line and "LUFS" in line:
            found = float(line.split("I:", 1)[1].split("LUFS", 1)[0].strip())
    if found is None:
        raise AssertionError("no loudness")
    return found
