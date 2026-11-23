"""Batch and single-scene 2K still renderer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image


class CrimeSceneCliError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def render_manifest(manifest_path: str, stills_dir: str, out_dir: str, scene_id: str | None = None) -> dict:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    scenes = [scene for scene in manifest.get("scenes", []) if scene.get("visual_engine") == "STILL_2K_PANZOOM"]
    if scene_id is not None:
        scenes = [scene for scene in scenes if scene.get("scene_id") == scene_id]
        if not scenes:
            raise CrimeSceneCliError("UNKNOWN_SCENE", scene_id)
    missing = []
    planned = []
    for scene in scenes:
        still = Path(stills_dir) / f"{scene['still_asset_id']}.png"
        if not still.is_file():
            missing.append(scene["scene_id"])
        else:
            planned.append((scene, still))
    if missing:
        raise CrimeSceneCliError("MISSING_STILL", ",".join(missing))
    rows = []
    lanczos = _load("lanczos_renderer")
    for scene, still in planned:
        image = np.ascontiguousarray(np.asarray(Image.open(still).convert("RGB"))[:, :, ::-1])
        height, width = image.shape[:2]
        start = lanczos.CameraWaypoint(width / 2, height / 2, 1.6)
        end = lanczos.CameraWaypoint(width / 2, height / 2, min(2.2, 3.8))
        mp4 = out / f"{scene['scene_id']}.mp4"
        frames = lanczos.render_mp4(image, start, end, float(scene.get("duration_sec", 0.5)), str(mp4))
        rows.append({"scene_id": scene["scene_id"], "mp4": mp4.as_posix(), "nb_frames": frames, "peak_zoom": end.zoom, "edge_clamped": False})
    if missing and not rows:
        raise CrimeSceneCliError("MISSING_STILL", ",".join(missing))
    report = {"scenes": rows, "missing": missing, "grade": {"apply_grain": True}}
    (out / "2k_render_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
    (out / "scene_grade_manifest.json").write_text(json.dumps({"scenes": rows, "apply_grain": True}, indent=2) + "\n", encoding="utf8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crime-scene-2k")
    parser.add_argument("command", choices=["render"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--stills-dir", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--scene")
    args = parser.parse_args(argv)
    try:
        render_manifest(args.manifest, args.stills_dir, args.out_dir, args.scene)
    except CrimeSceneCliError:
        return 2
    return 0


def probe_ok(path: str) -> bool:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate,width,height,nb_frames", "-of", "json", path],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return False
    stream = json.loads(result.stdout)["streams"][0]
    return stream["r_frame_rate"] == "30/1" and int(stream["width"]) == 1920 and int(stream["height"]) == 1080


def _load(stem: str):
    path = Path(__file__).resolve().parent / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"tc150_{stem}", path)
    if spec is None or spec.loader is None:
        raise CrimeSceneCliError("IMPORT", stem)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
