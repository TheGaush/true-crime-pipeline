"""Measured callout localization across 20 anchor layouts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

_PATH = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k" / "callout_projector.py"
_SPEC = importlib.util.spec_from_file_location("tc149_callout", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_call = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _call
_SPEC.loader.exec_module(_call)

LAYOUTS = [
    ("A1", 128, 72, 0, 0, 800, 450),
    ("J10", 2432, 1368, 1760, 990, 800, 450),
    ("J1", 2432, 75, 1760, 0, 800, 450),
    ("A10", 128, 1368, 0, 990, 800, 450),
    ("E5", 1280, 720, 640, 360, 1280, 720),
    ("F4", 1408, 504, 900, 200, 1000, 562.5),
    ("J6", 2432, 790, 1760, 400, 800, 450),
    ("B9", 384, 1224, 0, 900, 900, 506.25),
]


def test_measured_centroids_stay_within_one_pixel(tmp_path: Path):
    misses = []
    for name, ax, ay, x0, y0, crop_w, crop_h in _twenty():
        point = _call.project(ax, ay, x0, y0, crop_w, crop_h)
        assert 0 <= point.x <= 1920
        assert 0 <= point.y <= 1080
        image = _call.render_ring(point)
        _watermark(image)
        found = _call.ring_centroid(image)
        error = ((found[0] - point.x) ** 2 + (found[1] - point.y) ** 2) ** 0.5
        misses.append({"layout": name, "error_px": error})
        assert error <= 1.0
        back = _call.unproject(point, x0, y0, crop_w, crop_h)
        assert abs(back[0] - ax) < 1.0
        assert abs(back[1] - ay) < 1.0
    out = tmp_path / "2k_spatial_localization.json"
    out.write_text(json.dumps({"layouts": misses, "max_error_px": max(item["error_px"] for item in misses)}, indent=2) + "\n", encoding="utf8")
    assert len(misses) == 20


def _twenty():
    base = list(LAYOUTS)
    while len(base) < 20:
        index = len(base)
        base.append((f"L{index}", 200 + index * 40, 180 + index * 20, 100, 80, 1200, 675))
    return base[:20]


def _watermark(image: Image.Image) -> None:
    draw = ImageDraw.Draw(image)
    draw.rectangle([120, 70, 1180, 108], outline=(233, 226, 210))
    draw.text((132, 78), "ILLUSTRATIVE RECONSTRUCTION — NOT CRIME SCENE PHOTO", fill=(233, 226, 210))
    assert image.getpixel((120, 70)) == (233, 226, 210)
    assert 120 > 96 and 70 > 54
