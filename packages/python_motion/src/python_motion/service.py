"""Unified motion-asset API and command line.

Selective flags rebuild only the requested stage. Paths in the report use
forward slashes. A failed safety check is a non-zero exit.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path


class MotionServiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BuildRequest:
    manifest_path: str
    out_dir: str
    only_sfx: bool = False
    only_bookends: bool = False
    animatic: bool = False


def build_assets(request: BuildRequest) -> dict:
    manifest = json.loads(Path(request.manifest_path).read_text(encoding="utf8"))
    out = Path(request.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "episode_id": manifest.get("episode_id", "episode"),
        "bookends": [],
        "sfx": [],
        "trajectories": [],
        "animatic": None,
        "ok": True,
    }
    if not request.only_sfx:
        report["bookends"] = _bookends(manifest, out)
        report["trajectories"] = _trajectories(manifest, out)
    if not request.only_bookends:
        report["sfx"] = _sfx(manifest, out)
    if request.animatic and not request.only_sfx and not request.only_bookends:
        report["animatic"] = _animatic(manifest, out)
    report["ok"] = all(item["safety_passed"] for item in report["bookends"])
    path = out / "motion_assets_report.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf8")
    if not report["ok"]:
        raise MotionServiceError("SAFETY", "a bookend failed the safety check")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python_motion")
    parser.add_argument("command", choices=["build"])
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--only-sfx", action="store_true")
    parser.add_argument("--only-bookends", action="store_true")
    parser.add_argument("--animatic", action="store_true")
    args = parser.parse_args(argv)
    try:
        build_assets(BuildRequest(args.manifest, args.out_dir, args.only_sfx, args.only_bookends, args.animatic))
    except MotionServiceError:
        return 1
    return 0


def _bookends(manifest: dict, out: Path) -> list[dict]:
    book = _load("bookend_generator")
    rows = []
    for scene in manifest.get("scenes", []):
        if scene.get("visual_engine") != "FLOW_HERO_VIDEO":
            continue
        pair = book.BookendGenerator().generate(
            book.BookendRequest(
                scene["scene_id"],
                scene.get("prompt_mode", "TEXT_TO_VIDEO"),
                float(scene.get("duration_sec", 4)),
                str(out),
            )
        )
        rows.append(
            {
                "scene_id": pair.scene_id,
                "prompt_mode": pair.prompt_mode,
                "start_frame": _posix(pair.start_frame),
                "end_frame": _posix(pair.end_frame),
                "start_sha256": pair.start_sha256,
                "end_sha256": pair.end_sha256,
                "safety_passed": pair.safety_passed,
            }
        )
    return rows


def _sfx(manifest: dict, out: Path) -> list[dict]:
    sfx = _load("sfx_synth")
    engine = sfx.SfxSynthesizer()
    rows = []
    for index, cue in enumerate(manifest.get("sfx_cues", [])):
        made = engine.synthesize(
            sfx.SfxRequest(cue.get("cue_type", "paper_slide"), duration_ms=int(cue.get("duration_ms", 40)), seed=index, cache_dir=str(out / "sfx"))
        )
        rows.append({"cue_type": made.cue_type, "path": _posix(made.path), "sha256": made.sha256, "sample_rate_hz": made.sample_rate_hz})
    return rows


def _trajectories(manifest: dict, out: Path) -> list[dict]:
    engine = _load("trajectory_engine")
    renderer = engine.TrajectoryRenderer()
    rows = []
    for scene in manifest.get("scenes", []):
        points = scene.get("waypoints")
        if not points:
            continue
        path = out / f"{scene['scene_id']}_trajectory.mp4"
        request = engine.TrajectoryRequest(tuple(tuple(point) for point in points), float(scene.get("duration_sec", 0.4)), str(path), True, False)
        made = renderer.render_mp4(request)
        rows.append({"scene_id": scene["scene_id"], "path": _posix(str(made["path"])), "nb_frames": made["nb_frames"]})
    return rows


def _animatic(manifest: dict, out: Path) -> dict:
    builder = _load("animatic_builder")
    result = builder.build_animatic(manifest, str(out / "animatic"))
    return {"mp4": _posix(result.mp4_path), "pacing": _posix(result.telemetry_path), "total_duration_sec": result.total_duration_sec}


def _posix(path: str | None) -> str | None:
    if path is None:
        return None
    return Path(path).as_posix()


def _load(stem: str):
    path = Path(__file__).with_name(f"{stem}.py")
    spec = importlib.util.spec_from_file_location(f"tc141_{stem}", path)
    if spec is None or spec.loader is None:
        raise MotionServiceError("IMPORT", f"missing {stem}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
