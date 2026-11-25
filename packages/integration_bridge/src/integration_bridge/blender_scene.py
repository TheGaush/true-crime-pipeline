"""Launch the cinematic Blender scene. Blender stays a separate app."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

KITS = ("overview", "porch", "document", "merge", "desk", "scale")
CINEMATIC_VERSION = "1"
SCENE_FILE = Path(__file__).with_name("cinematic_scene.py")


def choose_kit(scene: dict) -> str:
    """Pick a built-in 3D set from the scene heading, then from the picture prompt."""
    heading = str(scene.get("heading", "")).lower()
    prompt = str(scene.get("image_prompt", "")).lower()
    if "warning" in heading or "synthetic" in heading:
        return "overview"
    for text in (heading, prompt):
        if any(word in text for word in ("ethic", "privacy", "balance", "scale", "timeline")):
            return "scale"
        if "redact" in text or "statement" in text or "document" in text or "archive" in text:
            return "document"
        if any(word in text for word in ("combin", "merg", "synthesis")):
            return "merge"
        if any(word in text for word in ("porch", "house", "street", "neighborhood")):
            return "porch"
        if any(word in text for word in ("case file", "dashboard", "building", "desk", "office", "board")):
            return "desk"
    return "overview"


def find_blender() -> str | None:
    """The Blender app on this machine, or nothing when it is not installed."""
    env = os.environ.get("BLENDER", "").strip()
    if env and Path(env).is_file():
        return env
    mac = Path("/Applications/Blender.app/Contents/MacOS/Blender")
    if mac.is_file():
        return str(mac)
    return shutil.which("blender")


def render_with_blender(
    binary: str,
    out_file: Path,
    seconds: float,
    kit: str,
    *,
    samples: int = 24,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    frame: int | None = None,
    heading: str = "Scene",
) -> None:
    """Render one cinematic scene. A PNG path, or frame, renders a single still."""
    out_file.parent.mkdir(parents=True, exist_ok=True)
    command = [
        binary,
        "--background",
        "--factory-startup",
        "--python",
        str(SCENE_FILE),
        "--",
        "--out",
        str(out_file),
        "--seconds",
        f"{max(2.0, seconds):.3f}",
        "--kit",
        kit if kit in KITS else "overview",
        "--fps",
        str(fps),
        "--samples",
        str(samples),
        "--width",
        str(width),
        "--height",
        str(height),
        "--heading",
        " ".join(heading.split())[:28] or "Scene",
    ]
    if frame is not None:
        command.extend(["--frame", str(frame)])
    result = subprocess.run(command, text=True)
    if result.returncode != 0 or not out_file.is_file():
        raise RuntimeError(
            "Blender did not finish the cinematic scene. "
            f"The scene file is {SCENE_FILE}."
        )
