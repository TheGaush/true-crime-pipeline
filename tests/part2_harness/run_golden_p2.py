"""Offline Part 2 golden check. No provider calls."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(package: str, stem: str):
    path = ROOT / "packages" / package / "src" / package / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"p2_{stem}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    call = load("crime_scene_2k", "callout_projector")
    point = call.project(1280, 720, 640, 360, 1280, 720)
    found = call.ring_centroid(call.render_ring(point))
    error = ((found[0] - point.x) ** 2 + (found[1] - point.y) ** 2) ** 0.5
    turbulence = 0
    for path in (ROOT / "packages/render_catalog/src/motifs").glob("*.tsx"):
        text = path.read_text(encoding="utf8")
        if "<feTurbulence" in text or "<feDisplacementMap" in text:
            turbulence += 1
    sfx = load("python_motion", "sfx_synth")
    cue = sfx.SfxSynthesizer().synthesize(sfx.SfxRequest("paper_slide", duration_ms=20, seed=1))
    metrics = {
        "episodes": ["ep_golden_01", "ep_golden_02", "ep_golden_03"],
        "remote_calls": 0,
        "turbulence_nodes": turbulence,
        "callout_error_px": error,
        "sfx_rate_hz": cue.sample_rate_hz,
        "motif_count": len(list((ROOT / "packages/render_catalog/src/motifs").glob("*.tsx"))),
    }
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "part2_harness_metrics.json"
    out.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf8")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from assertions import assert_metrics

    assert_metrics(str(out))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
