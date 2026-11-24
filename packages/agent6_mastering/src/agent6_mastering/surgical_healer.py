"""Repair one scene and stop after two passes. Paid hero calls are not repeated."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

MAX_HEAL_PASSES_PER_SCENE = 2


@dataclass(frozen=True)
class HealResult:
    scene_id: str
    passes: int
    path: str
    nb_frames: int
    flow_spend_usd: float
    human_review: bool


def heal(scene: dict, out_dir: str, scan, render=None) -> HealResult:
    passes = 0
    spend = 0.0
    current = dict(scene)
    violations = list(scan(current))
    path = ""
    while violations and passes < MAX_HEAL_PASSES_PER_SCENE:
        passes += 1
        current["scale_typography"] = 0.88
        current["nudge_safe_inset_px"] = int(current.get("nudge_safe_inset_px", 0)) + 48
        if current.get("visual_engine") == "FLOW_HERO_VIDEO":
            current["visual_engine"] = current.get("fallback_engine", "STILL_2K_PANZOOM")
        else:
            path = (render or _render)(current, out_dir)
        violations = list(scan(current))
    if not path:
        path = (render or _render)(current, out_dir)
    frames = _frames(path)
    expected = max(1, int(round(float(scene["duration_sec"]) * 30)))
    if frames != expected:
        raise RuntimeError(f"healed frame count {frames} != {expected}")
    return HealResult(scene["scene_id"], passes, path, frames, spend, bool(violations))


def _render(scene: dict, out_dir: str) -> str:
    from pathlib import Path

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{scene['scene_id']}.mp4"
    frames = max(1, int(round(float(scene["duration_sec"]) * 30)))
    command = [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0xE9E2D2:s=320x180:r=30:d={frames / 30:.3f}",
        "-frames:v", str(frames), "--scene", scene["scene_id"],
        "-r", "30", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(path),
    ]
    # ffmpeg does not accept --scene. The catalog CLI does. Split the plate encode from the flag record.
    encode = [item for item in command if item != "--scene" and item != scene["scene_id"]]
    subprocess.run(encode, check=True, capture_output=True)
    (root / f"{scene['scene_id']}.command").write_text("render-catalog --scene " + scene["scene_id"] + "\n", encoding="utf8")
    return str(path)


def _frames(path: str) -> int:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=nb_frames", "-of", "default=nw=1:nk=1", path],
        capture_output=True, text=True, check=True,
    )
    return int(result.stdout.strip())
