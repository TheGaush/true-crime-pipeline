"""Aspect and resolution stress for crop windows and the anchor loader."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1] / "src" / "crime_scene_2k"


def load(stem: str):
    spec = importlib.util.spec_from_file_location(f"tc151_{stem}", ROOT / f"{stem}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_crops_stay_inside_every_aspect():
    crop = load("crop_math")
    sizes = [(3840, 2160), (2560, 1440), (2048, 1152), (2048, 1536), (3440, 1440), (2400, 1800)]
    for width, height in sizes:
        window = crop.crop_window(width, height, "A", 1, 1, 1, target_zoom=1.6)
        window.assert_inside(width, height)
        assert window.crop_h <= height + 1e-6
        assert abs((window.crop_w / window.crop_h) - (16 / 9)) < 1e-4


def test_low_resolution_is_rejected_and_exif_size_is_the_stored_size(tmp_path: Path):
    loader = load("anchor_loader")
    small = tmp_path / "small.png"
    Image.new("RGB", (1280, 720), (233, 226, 210)).save(small)
    try:
        loader.load_anchors(str(small), [{"col": "A", "row": 1, "span_cols": 1, "span_rows": 1}])
        assert False
    except loader.AnchorBoundsError:
        pass
    wide = tmp_path / "wide.png"
    image = Image.new("RGB", (2560, 1440), (233, 226, 210))
    image.save(wide)
    transposed = ImageOps.exif_transpose(Image.open(wide))
    assert transposed.size == (2560, 1440)
    anchors = loader.load_anchors(str(wide), [{"col": "E", "row": 5, "span_cols": 2, "span_rows": 2}])
    assert 0 <= anchors[0].x_px <= 2560
