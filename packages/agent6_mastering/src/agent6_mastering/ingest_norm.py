"""Conform every timeline segment to 1920x1080 CFR 30 and 48 kHz."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

FPS = 30


@dataclass(frozen=True)
class NormalizedSegment:
    scene_id: str
    path: str
    nb_frames: int
    is_foia: bool
    exempt_from_grain: bool


def expected_frames(duration_sec: float) -> int:
    return max(1, int(round(duration_sec * FPS)))


def normalize(path: str, scene_id: str, out_dir: str, engine: str, duration_sec: float) -> NormalizedSegment:
    out = Path(out_dir) / f"{scene_id}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    frames = expected_frames(duration_sec)
    command = [
        "ffmpeg", "-y", "-i", path,
        "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
        "-shortest",
        "-vf", "fps=30,scale=1920:1080:force_original_aspect_ratio=decrease:flags=lanczos,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x1B1B1D",
        "-frames:v", str(frames),
        "-r", "30", "-pix_fmt", "yuv420p", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-ar", "48000", "-ac", "2",
        str(out),
    ]
    subprocess.run(command, check=True, capture_output=True)
    probe = _probe(str(out))
    if probe["r_frame_rate"] != "30/1" or probe["avg_frame_rate"] != "30/1":
        raise RuntimeError(f"{scene_id} is still variable frame rate")
    if probe["width"] != 1920 or probe["height"] != 1080 or probe["pix_fmt"] != "yuv420p":
        raise RuntimeError(f"{scene_id} missed the geometry gate")
    foia = engine == "FOIA_REAL_FOOTAGE"
    return NormalizedSegment(scene_id, out.as_posix(), int(probe["nb_frames"]), foia, foia)


def write_manifest(segments: list[NormalizedSegment], path: str) -> None:
    body = {
        "segments": [
            {
                "scene_id": item.scene_id,
                "path": item.path,
                "nb_frames": item.nb_frames,
                "is_foia": item.is_foia,
                "exempt_from_grain": item.exempt_from_grain,
            }
            for item in segments
        ]
    }
    Path(path).write_text(json.dumps(body, indent=2) + "\n", encoding="utf8")


def _probe(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,pix_fmt", "-of", "json", path],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)["streams"][0]
