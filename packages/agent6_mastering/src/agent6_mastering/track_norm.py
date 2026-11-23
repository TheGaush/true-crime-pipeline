"""Normalize one stem. A silent stem stays silent instead of failing the meter."""

from __future__ import annotations

import subprocess
from pathlib import Path


TARGETS = {1: -16.0, 2: -18.0, 3: -22.0}


def normalize_stem(source: str, track: int, out_path: str) -> dict:
    target = TARGETS[track]
    if _silent(source):
        _silence(source, out_path)
        return {"track": track, "integrated_lufs": None, "silent": True, "path": out_path}
    command = [
        "ffmpeg", "-y", "-i", source,
        "-af", f"loudnorm=I={target}:TP=-2.0:LRA=11:print_format=json",
        "-ar", "48000", "-c:a", "pcm_s16le", out_path,
    ]
    subprocess.run(command, capture_output=True, text=True, check=True)
    return {"track": track, "integrated_lufs": _measure(out_path), "silent": False, "target_lufs": target, "path": out_path}


def _silent(path: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-i", path, "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )
    return "max_volume: -inf" in result.stderr or "max_volume: -91" in result.stderr


def _silence(source: str, out_path: str) -> None:
    duration = _duration(source)
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=48000", "-t", f"{duration:.3f}", "-c:a", "pcm_s16le", out_path],
        check=True, capture_output=True,
    )


def _duration(path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip() or "0.1")


def _measure(path: str) -> float:
    result = subprocess.run(["ffmpeg", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True, check=False)
    found = None
    for line in result.stderr.splitlines():
        if "I:" in line and "LUFS" in line:
            found = float(line.split("I:", 1)[1].split("LUFS", 1)[0].strip())
    if found is None:
        raise RuntimeError("loudness meter produced no integrated reading")
    return found
